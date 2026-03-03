"""Tests for CaptureEngine and AnalysisEngine (engine.py)."""

import time
import threading
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from opencapture.config import Config
from opencapture.engine import CaptureEngine, AnalysisEngine


def _mock_backend(window_info=("App", "", "com.test")):
    """Create a mock PlatformBackend."""
    backend = MagicMock()
    backend.get_active_window_info.return_value = window_info
    backend.get_window_at_point.return_value = window_info
    backend.get_active_window_bounds.return_value = None
    backend.check_accessibility.return_value = True
    backend.get_key_symbols.return_value = {}
    def _start_observer(callback):
        callback(*window_info)
    backend.start_window_observer.side_effect = _start_observer
    backend.stop_window_observer.return_value = None
    backend.run_event_loop.return_value = None
    return backend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    cfg = Config()
    cfg.set("capture.output_dir", str(tmp_path))
    return cfg


# ---------------------------------------------------------------------------
# CaptureEngine — event subscription / dispatch
# ---------------------------------------------------------------------------

class TestCaptureEngineEvents:
    def test_subscribe_and_emit(self, config):
        engine = CaptureEngine(config)
        received = []
        engine.subscribe("keyboard", lambda t, d: received.append((t, d)))

        engine._emit("keyboard", {"line": "hello"})

        assert len(received) == 1
        assert received[0] == ("keyboard", {"line": "hello"})

    def test_wildcard_subscriber(self, config):
        engine = CaptureEngine(config)
        received = []
        engine.subscribe("*", lambda t, d: received.append(t))

        engine._emit("keyboard", {})
        engine._emit("screenshot", {})
        engine._emit("window", {})

        assert received == ["keyboard", "screenshot", "window"]

    def test_subscriber_type_filter(self, config):
        engine = CaptureEngine(config)
        received = []
        engine.subscribe("screenshot", lambda t, d: received.append(t))

        engine._emit("keyboard", {})
        engine._emit("screenshot", {})

        assert received == ["screenshot"]

    def test_subscriber_error_does_not_crash(self, config):
        engine = CaptureEngine(config)

        def bad_callback(t, d):
            raise RuntimeError("boom")

        engine.subscribe("*", bad_callback)
        # Should not raise
        engine._emit("keyboard", {"line": "test"})

    def test_multiple_subscribers(self, config):
        engine = CaptureEngine(config)
        a, b = [], []
        engine.subscribe("keyboard", lambda t, d: a.append(1))
        engine.subscribe("keyboard", lambda t, d: b.append(1))

        engine._emit("keyboard", {})

        assert len(a) == 1
        assert len(b) == 1


# ---------------------------------------------------------------------------
# CaptureEngine — start / stop lifecycle
# ---------------------------------------------------------------------------

class TestCaptureEngineLifecycle:
    def test_start_stop(self, config):
        backend = _mock_backend()
        engine = CaptureEngine(config)
        status_events = []
        engine.subscribe("status", lambda t, d: status_events.append(d))

        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            result = engine.start()

        assert result is None  # no error
        assert engine.is_running is True
        assert {"state": "started"} in status_events

        engine.stop()
        assert engine.is_running is False
        assert {"state": "stopped"} in status_events

    def test_double_start_is_noop(self, config):
        backend = _mock_backend()
        engine = CaptureEngine(config)
        with patch("opencapture.auto_capture.get_backend", return_value=backend):
            engine.start()
            result = engine.start()  # second start
        assert result is None
        engine.stop()

    def test_stop_without_start(self, config):
        engine = CaptureEngine(config)
        engine.stop()  # should not raise

    def test_start_failure_emits_error(self, config):
        engine = CaptureEngine(config)
        status_events = []
        engine.subscribe("status", lambda t, d: status_events.append(d))

        with patch("opencapture.auto_capture.AutoCapture") as MockAC:
            MockAC.side_effect = RuntimeError("permission denied")
            result = engine.start()

        assert result is not None
        assert "permission denied" in result
        assert engine.is_running is False
        assert any(e.get("state") == "error" for e in status_events)


# ---------------------------------------------------------------------------
# CaptureEngine — get_status
# ---------------------------------------------------------------------------

class TestCaptureEngineStatus:
    def test_status_when_not_running(self, config, tmp_path):
        engine = CaptureEngine(config)
        status = engine.get_status()

        assert status["running"] is False
        assert status["screenshots"] == 0
        assert status["logs"] == 0
        assert status["recordings"] == 0

    def test_status_counts_files(self, config, tmp_path):
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = tmp_path / today
        today_dir.mkdir()

        (today_dir / "click_001.webp").touch()
        (today_dir / "click_002.webp").touch()
        (today_dir / f"{today}.log").touch()
        (today_dir / "mic_001.wav").touch()

        engine = CaptureEngine(config)
        status = engine.get_status()

        assert status["screenshots"] == 2
        assert status["logs"] == 1
        assert status["recordings"] == 1

    def test_status_no_today_dir(self, config, tmp_path):
        engine = CaptureEngine(config)
        status = engine.get_status()
        assert status["screenshots"] == 0


# ---------------------------------------------------------------------------
# CaptureEngine — check_accessibility
# ---------------------------------------------------------------------------

class TestCheckAccessibility:
    def test_delegates_to_backend(self, config):
        backend = _mock_backend()
        backend.check_accessibility.return_value = True
        with patch("opencapture.platform.get_backend", return_value=backend):
            assert CaptureEngine.check_accessibility() is True


# ---------------------------------------------------------------------------
# AnalysisEngine — background loop lifecycle
# ---------------------------------------------------------------------------

class TestAnalysisEngineLifecycle:
    def test_start_stop(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        assert engine._thread is not None
        assert engine._thread.is_alive()
        assert engine._loop is not None
        assert engine._loop.is_running()

        engine.stop()

        assert engine._thread is None
        assert engine._loop is None

    def test_double_start(self, config):
        engine = AnalysisEngine(config)
        engine.start()
        engine.start()  # should not create a second thread
        engine.stop()

    def test_stop_without_start(self, config):
        engine = AnalysisEngine(config)
        engine.stop()  # should not raise

    def test_submit_without_start_calls_callback_with_error(self, config):
        engine = AnalysisEngine(config)
        cb = MagicMock()
        engine._submit(lambda: None, callback=cb)

        cb.assert_called_once()
        assert "error" in cb.call_args[0][0]

    def test_submit_runs_coroutine(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        result = {}
        event = threading.Event()

        async def task():
            return {"answer": 42}

        def on_done(r):
            result.update(r)
            event.set()

        engine._submit(task, callback=on_done)
        event.wait(timeout=5)

        assert result == {"answer": 42}
        engine.stop()

    def test_submit_exception_calls_callback_with_error(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        result = {}
        event = threading.Event()

        async def bad_task():
            raise ValueError("oops")

        def on_done(r):
            result.update(r)
            event.set()

        engine._submit(bad_task, callback=on_done)
        event.wait(timeout=5)

        assert "error" in result
        assert "oops" in result["error"]
        engine.stop()


# ---------------------------------------------------------------------------
# AnalysisEngine — health_check
# ---------------------------------------------------------------------------

class TestAnalysisEngineHealthCheck:
    def test_health_check_submits(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        result = {}
        event = threading.Event()

        def on_done(r):
            result.update(r)
            event.set()

        with patch("opencapture.analyzer.Analyzer") as MockAnalyzer:
            mock_instance = MagicMock()

            async def fake_health():
                return {"ollama": True}

            async def fake_close():
                pass

            mock_instance.health_check = fake_health
            mock_instance.close = fake_close
            MockAnalyzer.return_value = mock_instance

            engine.health_check(callback=on_done)
            event.wait(timeout=5)

        assert result.get("ollama") is True
        engine.stop()
