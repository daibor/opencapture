"""Tests for AutoCapture and WindowTracker (auto_capture.py)."""

import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

pytest.importorskip("pynput")

from opencapture.auto_capture import AutoCapture, WindowTracker


def _mock_backend(window_info=("App", "", "com.test")):
    """Create a mock PlatformBackend that returns the given window info."""
    backend = MagicMock()
    backend.get_active_window_info.return_value = window_info
    backend.get_window_at_point.return_value = window_info
    backend.get_active_window_bounds.return_value = None
    backend.check_accessibility.return_value = True
    backend.get_key_symbols.return_value = {}
    # start_window_observer: immediately call callback with initial info
    def _start_observer(callback):
        callback(*window_info)
    backend.start_window_observer.side_effect = _start_observer
    backend.stop_window_observer.return_value = None
    backend.run_event_loop.return_value = None
    return backend


# ---------------------------------------------------------------------------
# WindowTracker
# ---------------------------------------------------------------------------

class TestWindowTracker:
    def test_callback_on_start(self):
        """Starting the tracker fires the callback with initial window info."""
        cb = MagicMock()
        wt = WindowTracker(cb)

        backend = _mock_backend(("Finder", "Desktop", "com.apple.finder"))
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            wt.start()
            time.sleep(0.1)
            wt.stop()

        cb.assert_called()
        first_call = cb.call_args_list[0]
        assert first_call[0] == ("Finder", "Desktop", "com.apple.finder")

    def test_tracks_current_state(self):
        cb = MagicMock()
        wt = WindowTracker(cb)

        backend = _mock_backend(("Safari", "Google", "com.apple.Safari"))
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            wt.start()
            time.sleep(0.1)
            wt.stop()

        assert wt.current_app_name == "Safari"
        assert wt.current_window_title == "Google"
        assert wt.current_bundle_id == "com.apple.Safari"

    def test_detects_window_change_via_observer(self):
        """Observer callback detects when the active window changes."""
        cb = MagicMock()
        wt = WindowTracker(cb)

        backend = _mock_backend(("App1", "Win1", "com.app1"))
        # Capture the observer callback so we can invoke it manually
        observer_cb = None
        def _start_observer(callback):
            nonlocal observer_cb
            observer_cb = callback
            callback("App1", "Win1", "com.app1")
        backend.start_window_observer.side_effect = _start_observer

        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            wt.start()
            # Simulate window change via the observer
            observer_cb("App2", "Win2", "com.app2")
            wt.stop()

        app_names = [c[0][0] for c in cb.call_args_list]
        assert "App1" in app_names
        assert "App2" in app_names

    def test_stop_is_idempotent(self):
        cb = MagicMock()
        wt = WindowTracker(cb)
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            # Stopping without starting should not crash
            wt.stop()
            wt.stop()


# ---------------------------------------------------------------------------
# AutoCapture - constructor wiring
# ---------------------------------------------------------------------------

class TestAutoCaptureInit:
    def test_default_storage_dir(self):
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            ac = AutoCapture()
        assert ac.storage_dir == Path.home() / "opencapture"

    def test_custom_storage_dir(self, tmp_path):
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            ac = AutoCapture(storage_dir=str(tmp_path / "custom"))
        assert ac.storage_dir == tmp_path / "custom"
        assert ac.storage_dir.exists()

    def test_key_logger_created(self, tmp_path):
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            ac = AutoCapture(storage_dir=str(tmp_path))
        assert ac.key_logger is not None
        assert ac.key_logger.storage_dir == tmp_path

    def test_mouse_capture_linked_to_key_logger(self, tmp_path):
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            ac = AutoCapture(storage_dir=str(tmp_path))
        assert ac.mouse_capture.key_logger is ac.key_logger

    def test_window_tracker_created(self, tmp_path):
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            ac = AutoCapture(storage_dir=str(tmp_path))
        assert ac.window_tracker is not None

    def test_on_event_wired_to_key_logger(self, tmp_path):
        cb = MagicMock()
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            ac = AutoCapture(storage_dir=str(tmp_path), on_event=cb)
        assert ac.key_logger._on_event is cb

    def test_mic_disabled_by_default(self, tmp_path):
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            ac = AutoCapture(storage_dir=str(tmp_path))
        assert ac.mic_capture is None

    def test_mic_returns_none_when_unavailable(self, tmp_path):
        """mic_enabled=True with no platform support should not crash."""
        backend = _mock_backend()
        with patch("opencapture.auto_capture.get_backend", return_value=backend), \
             patch("opencapture.mic.create_mic_capture", return_value=None):
            ac = AutoCapture(storage_dir=str(tmp_path), mic_enabled=True)
        assert ac.mic_capture is None


# ---------------------------------------------------------------------------
# AutoCapture - start / stop lifecycle
# ---------------------------------------------------------------------------

class TestAutoCaptureLifecycle:
    """Lifecycle tests mock pynput listeners to avoid macOS HIToolbox abort
    (Quartz Event Taps require the main-thread CFRunLoop)."""

    def _patches(self, backend):
        """Context manager that mocks both get_backend and pynput listeners."""
        return patch.multiple(
            "opencapture.auto_capture",
            get_backend=MagicMock(return_value=backend),
            keyboard=MagicMock(),
            mouse=MagicMock(),
        )

    def test_start_creates_listeners(self, tmp_path):
        backend = _mock_backend()
        with self._patches(backend):
            ac = AutoCapture(storage_dir=str(tmp_path))
            ac.start()

        assert ac._keyboard_listener is not None
        assert ac._mouse_listener is not None
        assert ac._running is True

        ac.stop()
        assert ac._running is False

    def test_stop_flushes_key_logger(self, tmp_path):
        backend = _mock_backend()
        with self._patches(backend):
            ac = AutoCapture(storage_dir=str(tmp_path))
            ac.key_logger.flush = MagicMock()
            ac.start()
            ac.stop()

        ac.key_logger.flush.assert_called_once()

    def test_stop_waits_for_mouse_pending(self, tmp_path):
        backend = _mock_backend()
        with self._patches(backend):
            ac = AutoCapture(storage_dir=str(tmp_path))
            ac.mouse_capture.wait_for_pending = MagicMock()
            ac.start()
            ac.stop()

        ac.mouse_capture.wait_for_pending.assert_called_once()


# ---------------------------------------------------------------------------
# AutoCapture - accessibility check
# ---------------------------------------------------------------------------

class TestAccessibilityCheck:
    def test_delegates_to_backend(self):
        backend = _mock_backend()
        backend.check_accessibility.return_value = True
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            assert AutoCapture._check_accessibility() is True
            backend.check_accessibility.assert_called_with(prompt=False)

    def test_prompt_passed_through(self):
        backend = _mock_backend()
        backend.check_accessibility.return_value = True
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            AutoCapture._check_accessibility(prompt=True)
            backend.check_accessibility.assert_called_with(prompt=True)


# ---------------------------------------------------------------------------
# AutoCapture - listener validation on start
# ---------------------------------------------------------------------------

class TestListenerValidation:
    """Verify that AutoCapture.start() detects dead listeners."""

    def test_keyboard_listener_failure_raises(self, tmp_path):
        backend = _mock_backend()
        mock_keyboard = MagicMock()
        mock_mouse = MagicMock()

        # Keyboard listener dies immediately (is_alive returns False)
        mock_kb_listener = MagicMock()
        mock_kb_listener.is_alive.return_value = False
        mock_keyboard.Listener.return_value = mock_kb_listener

        with patch.multiple(
            "opencapture.auto_capture",
            get_backend=MagicMock(return_value=backend),
            keyboard=mock_keyboard,
            mouse=mock_mouse,
        ):
            ac = AutoCapture(storage_dir=str(tmp_path))
            with pytest.raises(RuntimeError, match="Keyboard listener failed"):
                ac.start()

    def test_mouse_listener_failure_raises(self, tmp_path):
        backend = _mock_backend()
        mock_keyboard = MagicMock()
        mock_mouse = MagicMock()

        # Keyboard listener succeeds
        mock_kb_listener = MagicMock()
        mock_kb_listener.is_alive.return_value = True
        mock_keyboard.Listener.return_value = mock_kb_listener

        # Mouse listener dies immediately
        mock_mouse_listener = MagicMock()
        mock_mouse_listener.is_alive.return_value = False
        mock_mouse.Listener.return_value = mock_mouse_listener

        with patch.multiple(
            "opencapture.auto_capture",
            get_backend=MagicMock(return_value=backend),
            keyboard=mock_keyboard,
            mouse=mock_mouse,
        ):
            ac = AutoCapture(storage_dir=str(tmp_path))
            with pytest.raises(RuntimeError, match="Mouse listener failed"):
                ac.start()

    def test_successful_start_with_validation(self, tmp_path):
        backend = _mock_backend()
        mock_keyboard = MagicMock()
        mock_mouse = MagicMock()

        # Both listeners stay alive
        mock_kb_listener = MagicMock()
        mock_kb_listener.is_alive.return_value = True
        mock_keyboard.Listener.return_value = mock_kb_listener

        mock_mouse_listener = MagicMock()
        mock_mouse_listener.is_alive.return_value = True
        mock_mouse.Listener.return_value = mock_mouse_listener

        with patch.multiple(
            "opencapture.auto_capture",
            get_backend=MagicMock(return_value=backend),
            keyboard=mock_keyboard,
            mouse=mock_mouse,
        ):
            ac = AutoCapture(storage_dir=str(tmp_path))
            ac.start()  # Should not raise
            assert ac._running is True
            ac.stop()
