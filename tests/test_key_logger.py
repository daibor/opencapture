"""Tests for KeyLogger (auto_capture.py)."""

import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pynput.keyboard import Key, KeyCode

from opencapture.auto_capture import KeyLogger


def _mock_backend(window_info=("App", "", "com.test")):
    """Create a mock PlatformBackend."""
    backend = MagicMock()
    backend.get_active_window_info.return_value = window_info
    backend.get_key_symbols.return_value = {
        Key.enter: '\u21a9',
        Key.tab: '\u21e5',
        Key.space: ' ',
        Key.backspace: '\u232b',
        Key.delete: '\u2326',
        Key.esc: '\u238b',
        Key.shift: '\u21e7', Key.shift_l: '\u21e7', Key.shift_r: '\u21e7',
        Key.ctrl: '\u2303', Key.ctrl_l: '\u2303', Key.ctrl_r: '\u2303',
        Key.alt: '\u2325', Key.alt_l: '\u2325', Key.alt_r: '\u2325', Key.alt_gr: '\u2325',
        Key.cmd: '\u2318', Key.cmd_l: '\u2318', Key.cmd_r: '\u2318',
        Key.caps_lock: '\u21ea',
        Key.up: '\u2191', Key.down: '\u2193', Key.left: '\u2190', Key.right: '\u2192',
        Key.home: '\u2196', Key.end: '\u2198',
        Key.page_up: '\u21de', Key.page_down: '\u21df',
        Key.f1: 'F1', Key.f2: 'F2', Key.f3: 'F3', Key.f4: 'F4',
        Key.f5: 'F5', Key.f6: 'F6', Key.f7: 'F7', Key.f8: 'F8',
        Key.f9: 'F9', Key.f10: 'F10', Key.f11: 'F11', Key.f12: 'F12',
    }
    return backend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_backend():
    """Patch get_backend for all tests in this module."""
    backend = _mock_backend()
    with patch("opencapture.auto_capture.get_backend", return_value=backend):
        yield backend


@pytest.fixture()
def logger(tmp_path, patch_backend):
    """Return a KeyLogger writing to tmp_path."""
    return KeyLogger(tmp_path)


@pytest.fixture()
def logger_with_callback(tmp_path, patch_backend):
    """Return (KeyLogger, callback_mock)."""
    cb = MagicMock()
    return KeyLogger(tmp_path, on_event=cb), cb


def _set_window(logger, app="Terminal", title="bash", bundle="com.apple.Terminal"):
    """Set the active window state on a KeyLogger."""
    logger._current_app_name = app
    logger._current_window_title = title
    logger._current_bundle_id = bundle


def _read_log(tmp_path):
    """Read the first .log file under tmp_path (any date subdirectory)."""
    logs = list(tmp_path.rglob("*.log"))
    if not logs:
        return ""
    return logs[0].read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Basic key press → flush → log file
# ---------------------------------------------------------------------------

class TestKeyPress:
    def test_regular_chars(self, logger, tmp_path):
        for ch in "hello":
            logger.on_key_press(KeyCode.from_char(ch))
        logger.flush()

        text = _read_log(tmp_path)
        assert "hello" in text

    def test_special_keys(self, logger, tmp_path):
        logger.on_key_press(Key.enter)
        logger.on_key_press(Key.tab)
        logger.on_key_press(Key.backspace)
        logger.flush()

        text = _read_log(tmp_path)
        assert "\u21a9" in text  # enter
        assert "\u21e5" in text  # tab
        assert "\u232b" in text  # backspace

    def test_modifier_keys(self, logger, tmp_path):
        logger.on_key_press(Key.cmd)
        logger.on_key_press(Key.shift)
        logger.on_key_press(Key.ctrl)
        logger.on_key_press(Key.alt)
        logger.flush()

        text = _read_log(tmp_path)
        assert "\u2318" in text  # cmd
        assert "\u21e7" in text  # shift
        assert "\u2303" in text  # ctrl
        assert "\u2325" in text  # alt

    def test_unknown_key(self, logger, tmp_path):
        """Keys not in SPECIAL_KEYS and without .char get bracketed."""
        class WeirdKey:
            pass
        logger.on_key_press(WeirdKey())
        logger.flush()

        text = _read_log(tmp_path)
        assert "[" in text  # bracketed representation

    def test_empty_flush_no_file(self, logger, tmp_path):
        """Flush with no accumulated keys should not create a log file."""
        logger.flush()
        assert list(tmp_path.rglob("*.log")) == []


# ---------------------------------------------------------------------------
# Time clustering (20 s gap → new line)
# ---------------------------------------------------------------------------

class TestClustering:
    def test_time_gap_starts_new_line(self, logger, tmp_path):
        """A gap > CLUSTER_INTERVAL forces a flush and new keyboard line."""
        logger.on_key_press(KeyCode.from_char("a"))

        # Simulate time passing beyond cluster interval
        logger.last_key_time = time.time() - (KeyLogger.CLUSTER_INTERVAL + 1)

        logger.on_key_press(KeyCode.from_char("b"))
        logger.flush()

        text = _read_log(tmp_path)
        # Should have two ⌨️ lines: one for "a", one for "b"
        assert text.count("\u2328\ufe0f") == 2

    def test_no_gap_same_line(self, logger, tmp_path):
        logger.on_key_press(KeyCode.from_char("a"))
        logger.on_key_press(KeyCode.from_char("b"))
        logger.flush()

        text = _read_log(tmp_path)
        assert text.count("\u2328\ufe0f") == 1
        assert "ab" in text


# ---------------------------------------------------------------------------
# Window change → flush current line + header
# ---------------------------------------------------------------------------

class TestWindowChange:
    def test_on_window_activated_defers_header(self, logger, tmp_path):
        """Header is NOT written on window activation alone (deferred)."""
        logger.on_window_activated("Safari", "Google", "com.apple.Safari")

        text = _read_log(tmp_path)
        assert text == "", "header should be deferred until activity"

    def test_on_window_activated_writes_header_on_activity(self, logger, tmp_path):
        """Header appears once actual activity triggers it."""
        logger.on_window_activated("Safari", "Google", "com.apple.Safari")
        logger.log_screenshot("click_test.webp", "click", 100, 200)

        text = _read_log(tmp_path)
        assert "Safari" in text
        assert "Google" in text
        assert "com.apple.Safari" in text

    def test_on_window_activated_no_title(self, logger, tmp_path):
        logger.on_window_activated("Finder", "", "com.apple.finder")
        logger.log_screenshot("click_test.webp", "click", 100, 200)

        text = _read_log(tmp_path)
        assert "Finder" in text
        assert "com.apple.finder" in text

    def test_window_change_flushes_pending_keys(self, logger, tmp_path):
        logger.on_key_press(KeyCode.from_char("x"))
        # Now switch window
        logger.on_window_activated("App2", "", "com.test2")

        text = _read_log(tmp_path)
        # "x" should be flushed before the new header
        assert "x" in text

    def test_same_app_no_duplicate_header(self, logger, tmp_path):
        logger.on_window_activated("Safari", "Tab1", "com.apple.Safari")
        logger.on_window_activated("Safari", "Tab2", "com.apple.Safari")
        logger.log_screenshot("click_test.webp", "click", 100, 200)

        text = _read_log(tmp_path)
        # Same app name → header line written only once
        header_lines = [l for l in text.splitlines() if l.strip().startswith("[") and "Safari" in l]
        assert len(header_lines) == 1

    def test_key_after_window_switch_new_cluster(self, logger, tmp_path, patch_backend):
        """Keys typed after a window switch start in a new cluster."""
        patch_backend.get_active_window_info.return_value = ("App1", "", "com.test1")
        logger.on_key_press(KeyCode.from_char("a"))

        patch_backend.get_active_window_info.return_value = ("App2", "", "com.test2")
        logger.on_key_press(KeyCode.from_char("b"))
        logger.flush()

        text = _read_log(tmp_path)
        assert text.count("\u2328\ufe0f") == 2


# ---------------------------------------------------------------------------
# log_screenshot
# ---------------------------------------------------------------------------

class TestLogScreenshot:
    def test_click_entry(self, logger, tmp_path):
        _set_window(logger)
        logger.log_screenshot("click_120000_001_left_x100_y200.webp",
                              "click", 100, 200)

        text = _read_log(tmp_path)
        assert "\U0001f4f7" in text  # 📷
        assert "click_120000_001_left_x100_y200.webp" in text

    def test_drag_entry(self, logger, tmp_path):
        _set_window(logger)
        logger.log_screenshot("drag_120000_001_left_x10_y20_to_x30_y40.webp",
                              "drag", 10, 20, x2=30, y2=40)

        text = _read_log(tmp_path)
        assert "drag_120000_001_left_x10_y20_to_x30_y40.webp" in text

    def test_screenshot_writes_header_on_new_app(self, logger, tmp_path):
        _set_window(logger, app="Chrome")
        logger.log_screenshot("click_120000_001_left_x0_y0.webp", "click", 0, 0)

        text = _read_log(tmp_path)
        assert "Chrome" in text


# ---------------------------------------------------------------------------
# log_mic_event
# ---------------------------------------------------------------------------

class TestLogMicEvent:
    def test_mic_start(self, logger, tmp_path):
        logger.log_mic_event("mic_start", "FaceTime", timestamp="2026-01-01 10:00:00")

        text = _read_log(tmp_path)
        assert "\U0001f3a4" in text  # 🎤
        assert "mic_start" in text
        assert "FaceTime" in text

    def test_mic_stop_format(self, logger, tmp_path):
        """mic_stop uses space separator (not |)."""
        logger.log_mic_event("mic_stop", "dur=5s", timestamp="2026-01-01 10:00:05")

        text = _read_log(tmp_path)
        assert "mic_stop dur=5s" in text
        assert "|" not in text.split("mic_stop")[1]

    def test_mic_auto_timestamp(self, logger, tmp_path):
        logger.log_mic_event("mic_join", "Zoom")
        text = _read_log(tmp_path)
        assert "mic_join" in text


# ---------------------------------------------------------------------------
# on_event callback
# ---------------------------------------------------------------------------

class TestOnEventCallback:
    def test_keyboard_event(self, logger_with_callback, tmp_path):
        logger, cb = logger_with_callback
        logger.on_key_press(KeyCode.from_char("z"))
        logger.flush()

        cb.assert_called()
        args = cb.call_args_list[-1]
        assert args[0][0] == "keyboard"
        assert "z" in args[0][1]["line"]

    def test_screenshot_event(self, logger_with_callback, tmp_path):
        logger, cb = logger_with_callback
        _set_window(logger)
        logger.log_screenshot("test.webp", "click", 0, 0)

        cb.assert_called_once_with("screenshot", {
            "filename": "test.webp", "action": "click", "x": 0, "y": 0
        })

    def test_window_event(self, logger_with_callback, tmp_path):
        logger, cb = logger_with_callback
        logger.on_window_activated("Safari", "Google", "com.apple.Safari")

        cb.assert_called_once_with("window", {
            "app": "Safari", "title": "Google", "bundle_id": "com.apple.Safari"
        })

    def test_mic_event(self, logger_with_callback, tmp_path):
        logger, cb = logger_with_callback
        logger.log_mic_event("mic_start", "Zoom")

        cb.assert_called_once_with("mic", {
            "event_type": "mic_start", "detail": "Zoom"
        })


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_key_presses(self, logger, tmp_path):
        """Multiple threads pressing keys should not crash."""
        errors = []

        def press_keys():
            try:
                for ch in "abcde":
                    logger.on_key_press(KeyCode.from_char(ch))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=press_keys) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        logger.flush()
        assert not errors
        # All chars should be in the log (order may vary across lines)
        text = _read_log(tmp_path)
        char_count = sum(1 for c in text if c in "abcde")
        assert char_count >= 25  # at least 25 chars logged (may span multiple lines)


# ---------------------------------------------------------------------------
# Log file date directory structure
# ---------------------------------------------------------------------------

class TestLogFileStructure:
    def test_creates_date_subdirectory(self, logger, tmp_path):
        logger.on_key_press(KeyCode.from_char("x"))
        logger.flush()

        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        # Directory name should be a date YYYY-MM-DD
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", dirs[0].name)

    def test_log_filename_matches_date(self, logger, tmp_path):
        logger.on_key_press(KeyCode.from_char("x"))
        logger.flush()

        log_files = list(tmp_path.rglob("*.log"))
        assert len(log_files) == 1
        # Log file named YYYY-MM-DD.log
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}\.log", log_files[0].name)


# ---------------------------------------------------------------------------
# Timestamp ordering — keyboard buffer flushed before screenshot/mic
# ---------------------------------------------------------------------------

class TestTimestampOrdering:
    def test_keyboard_flushed_before_screenshot(self, logger, tmp_path):
        """Buffered keyboard line must appear before the screenshot line."""
        _set_window(logger)
        # Accumulate some keys (not yet flushed to disk)
        for ch in "abc":
            logger.on_key_press(KeyCode.from_char(ch))

        # Screenshot should flush the pending keyboard buffer first
        logger.log_screenshot("click_120000_001_left_x50_y50.webp", "click", 50, 50)

        text = _read_log(tmp_path)
        kb_pos = text.find("\u2328\ufe0f")   # ⌨️
        ss_pos = text.find("\U0001f4f7")      # 📷
        assert kb_pos != -1, "keyboard line missing"
        assert ss_pos != -1, "screenshot line missing"
        assert kb_pos < ss_pos, (
            f"keyboard (pos {kb_pos}) should come before screenshot (pos {ss_pos})"
        )

    def test_keyboard_flushed_before_mic_event(self, logger, tmp_path):
        """Buffered keyboard line must appear before the mic event line."""
        _set_window(logger)
        for ch in "xyz":
            logger.on_key_press(KeyCode.from_char(ch))

        logger.log_mic_event("mic_start", "FaceTime", timestamp="2026-01-01 10:00:00")

        text = _read_log(tmp_path)
        kb_pos = text.find("\u2328\ufe0f")   # ⌨️
        mic_pos = text.find("\U0001f3a4")     # 🎤
        assert kb_pos != -1, "keyboard line missing"
        assert mic_pos != -1, "mic line missing"
        assert kb_pos < mic_pos, (
            f"keyboard (pos {kb_pos}) should come before mic (pos {mic_pos})"
        )
