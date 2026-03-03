"""Tests for MouseCapture (auto_capture.py)."""

import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from pynput.mouse import Button

from opencapture.auto_capture import MouseCapture, KeyLogger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def key_logger(tmp_path):
    kl = KeyLogger(tmp_path)
    kl._current_app_name = "TestApp"
    kl._current_window_title = "TestWindow"
    kl._current_bundle_id = "com.test"
    return kl


@pytest.fixture()
def mc(tmp_path, key_logger):
    """MouseCapture with mocked _capture_and_save to avoid real screenshots."""
    mc = MouseCapture(tmp_path, key_logger)
    mc._capture_and_save = MagicMock()
    mc._get_window_at_point = MagicMock(
        return_value=("TestApp", "TestWindow", "com.test")
    )
    return mc


def _click(mc, x, y, button=Button.left, delay_ms=0):
    """Simulate a full press+release click."""
    if delay_ms:
        time.sleep(delay_ms / 1000.0)
    mc.on_click(x, y, button, True)   # press
    mc.on_click(x, y, button, False)  # release


# ---------------------------------------------------------------------------
# Single click
# ---------------------------------------------------------------------------

class TestSingleClick:
    def test_single_click_fires_after_delay(self, mc):
        """A single click fires after the double-click wait window."""
        _click(mc, 100, 200)
        mc.wait_for_pending()

        mc._capture_and_save.assert_called_once()
        args = mc._capture_and_save.call_args
        assert args[0][0] == "click"  # action
        assert args[0][2] == 100      # x
        assert args[0][3] == 200      # y

    def test_click_button_name(self, mc):
        _click(mc, 50, 50, Button.right)
        mc.wait_for_pending()

        args = mc._capture_and_save.call_args
        assert args[0][1] == "right"  # button_name

    def test_click_passes_window_info(self, mc):
        _click(mc, 10, 20)
        mc.wait_for_pending()

        args = mc._capture_and_save.call_args
        assert args[1]["window_info"] == ("TestApp", "TestWindow", "com.test")


# ---------------------------------------------------------------------------
# Double click
# ---------------------------------------------------------------------------

class TestDoubleClick:
    def test_double_click_detected(self, mc):
        """Two clicks within DOUBLE_CLICK_INTERVAL and DISTANCE → dblclick."""
        _click(mc, 100, 200)
        # Reset throttle so second click is not ignored
        with mc._lock:
            mc._last_capture_time = 0
        # Second click immediately (well within 400ms window)
        _click(mc, 101, 200)
        mc.wait_for_pending()

        # Should have exactly one call with action="dblclick"
        actions = [c[0][0] for c in mc._capture_and_save.call_args_list]
        assert "dblclick" in actions
        # The pending single click should have been cancelled
        assert actions.count("click") == 0

    def test_no_double_click_if_too_far(self, mc):
        """Two clicks far apart in space → two separate clicks."""
        _click(mc, 100, 200)

        # Second click far away (beyond DOUBLE_CLICK_DISTANCE=5)
        time.sleep(0.01)  # tiny delay to avoid throttle
        with mc._lock:
            mc._last_capture_time = 0  # reset throttle
        _click(mc, 200, 300)

        mc.wait_for_pending()

        actions = [c[0][0] for c in mc._capture_and_save.call_args_list]
        assert "dblclick" not in actions

    def test_no_double_click_if_too_slow(self, mc):
        """Two clicks with a long gap → two separate clicks."""
        _click(mc, 100, 200)

        # Fake the last click time to be old
        with mc._lock:
            mc._last_click_time = time.time() * 1000 - 1000  # 1 second ago
            mc._last_capture_time = 0

        _click(mc, 100, 200)
        mc.wait_for_pending()

        actions = [c[0][0] for c in mc._capture_and_save.call_args_list]
        assert "dblclick" not in actions


# ---------------------------------------------------------------------------
# Drag
# ---------------------------------------------------------------------------

class TestDrag:
    def test_drag_detected(self, mc):
        """Press at one point, release far away → drag."""
        mc.on_click(100, 200, Button.left, True)   # press
        mc.on_click(300, 400, Button.left, False)   # release far away

        mc.wait_for_pending()

        mc._capture_and_save.assert_called_once()
        args = mc._capture_and_save.call_args
        assert args[0][0] == "drag"
        assert args[0][2] == 100   # press x
        assert args[0][3] == 200   # press y
        assert args[0][4] == 300   # release x
        assert args[0][5] == 400   # release y

    def test_short_drag_is_click(self, mc):
        """Movement below DRAG_THRESHOLD → click, not drag."""
        mc.on_click(100, 200, Button.left, True)
        mc.on_click(102, 201, Button.left, False)  # only ~2px

        mc.wait_for_pending()

        args = mc._capture_and_save.call_args
        assert args[0][0] == "click"

    def test_drag_cancels_pending_click(self, mc):
        """If a single click is pending, drag should cancel it."""
        # First click to set up pending timer
        _click(mc, 50, 50)

        # Now drag before the timer fires
        with mc._lock:
            mc._last_capture_time = 0
        mc.on_click(100, 200, Button.left, True)
        mc.on_click(300, 400, Button.left, False)

        mc.wait_for_pending()

        actions = [c[0][0] for c in mc._capture_and_save.call_args_list]
        assert "drag" in actions


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------

class TestThrottling:
    def test_rapid_clicks_throttled(self, mc):
        """Clicks within THROTTLE_MS are ignored."""
        mc.on_click(100, 200, Button.left, True)
        mc.on_click(100, 200, Button.left, False)
        # Immediate second click (within 100ms throttle)
        mc.on_click(100, 200, Button.left, True)
        mc.on_click(100, 200, Button.left, False)

        mc.wait_for_pending()

        # Only one capture should have fired
        assert mc._capture_and_save.call_count == 1


# ---------------------------------------------------------------------------
# Distance calculation
# ---------------------------------------------------------------------------

class TestDistance:
    def test_zero_distance(self, mc):
        assert mc._distance(0, 0, 0, 0) == 0.0

    def test_horizontal(self, mc):
        assert mc._distance(0, 0, 3, 0) == 3.0

    def test_vertical(self, mc):
        assert mc._distance(0, 0, 0, 4) == 4.0

    def test_diagonal(self, mc):
        assert mc._distance(0, 0, 3, 4) == 5.0


# ---------------------------------------------------------------------------
# _capture_and_save (real method, mock mss/PIL)
# ---------------------------------------------------------------------------

class TestCaptureAndSave:
    def test_filename_format_click(self, tmp_path, key_logger):
        mc = MouseCapture(tmp_path, key_logger)

        fake_screenshot = MagicMock()
        fake_screenshot.size = (1920, 1080)
        fake_screenshot.bgra = b"\x00" * (1920 * 1080 * 4)

        with patch("opencapture.auto_capture.mss.mss") as mock_mss, \
             patch("opencapture.auto_capture.Image") as mock_image:
            mock_ctx = MagicMock()
            mock_ctx.monitors = [{"left": 0, "top": 0}]
            mock_ctx.grab.return_value = fake_screenshot
            mock_mss.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_mss.return_value.__exit__ = MagicMock(return_value=False)

            fake_img = MagicMock()
            mock_image.frombytes.return_value = fake_img
            mock_image.new.return_value = MagicMock()

            mc._get_active_window_bounds = MagicMock(return_value=None)

            mc._capture_and_save("click", "left", 100, 200)

        # Verify the key_logger got a screenshot event
        assert key_logger._on_event is None  # no callback, but log_screenshot was called
        logs = list(tmp_path.rglob("*.log"))
        assert len(logs) == 1
        text = logs[0].read_text()
        assert "click" in text
        assert "(100,200)" in text

    def test_filename_format_drag(self, tmp_path, key_logger):
        mc = MouseCapture(tmp_path, key_logger)

        fake_screenshot = MagicMock()
        fake_screenshot.size = (1920, 1080)
        fake_screenshot.bgra = b"\x00" * (1920 * 1080 * 4)

        with patch("opencapture.auto_capture.mss.mss") as mock_mss, \
             patch("opencapture.auto_capture.Image") as mock_image:
            mock_ctx = MagicMock()
            mock_ctx.monitors = [{"left": 0, "top": 0}]
            mock_ctx.grab.return_value = fake_screenshot
            mock_mss.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_mss.return_value.__exit__ = MagicMock(return_value=False)

            fake_img = MagicMock()
            mock_image.frombytes.return_value = fake_img
            mock_image.new.return_value = MagicMock()

            mc._get_active_window_bounds = MagicMock(return_value=None)

            mc._capture_and_save("drag", "left", 10, 20, 30, 40)

        logs = list(tmp_path.rglob("*.log"))
        text = logs[0].read_text()
        assert "drag" in text
        assert "(10,20)->(30,40)" in text


# ---------------------------------------------------------------------------
# wait_for_pending
# ---------------------------------------------------------------------------

class TestWaitForPending:
    def test_fires_pending_click_on_wait(self, mc):
        """wait_for_pending should fire any queued pending click."""
        _click(mc, 100, 200)
        # Don't wait for timer; call wait_for_pending immediately
        mc.wait_for_pending()

        mc._capture_and_save.assert_called()
        args = mc._capture_and_save.call_args
        assert args[0][0] == "click"

    def test_no_crash_when_nothing_pending(self, mc):
        mc.wait_for_pending()  # should not raise
