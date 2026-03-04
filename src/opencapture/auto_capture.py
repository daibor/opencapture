#!/usr/bin/env python3
"""
Auto Capture - Cross-platform keyboard and mouse activity collection tool.

Platform-specific logic (window info, accessibility, event loops) is
delegated to the `platform` backend package. This module contains only
business logic: keyboard logging, mouse capture, screenshot composition.
"""

import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from pynput import keyboard, mouse
from PIL import Image, ImageDraw
import mss

from opencapture.platform import get_backend


# ── WindowTracker ─────────────────────────────────────────


class WindowTracker:
    """Track active window changes via the platform backend."""

    def __init__(self, on_window_change):
        self.on_window_change = on_window_change
        self.current_app_name: Optional[str] = None
        self.current_window_title: Optional[str] = None
        self.current_bundle_id: Optional[str] = None

    def start(self):
        """Start window change monitoring."""
        backend = get_backend()
        # Get initial window info
        app_name, window_title, bundle_id = backend.get_active_window_info()
        self.current_app_name = app_name
        self.current_window_title = window_title
        self.current_bundle_id = bundle_id
        self.on_window_change(app_name, window_title, bundle_id)

        backend.start_window_observer(self._on_window_changed)

    def _on_window_changed(self, app_name: str, window_title: str, bundle_id: str):
        self.current_app_name = app_name
        self.current_window_title = window_title
        self.current_bundle_id = bundle_id
        self.on_window_change(app_name, window_title, bundle_id)

    def stop(self):
        """Stop monitoring."""
        get_backend().stop_window_observer()


class KeyLogger:
    """Keyboard logger with time clustering and window grouping."""

    CLUSTER_INTERVAL = 20  # 20s clustering interval

    # Current window state
    _current_app_name: str = ""
    _current_window_title: str = ""
    _current_bundle_id: str = ""

    def __init__(self, storage_dir: Path, on_event=None):
        self.storage_dir = storage_dir
        self.current_line = ""
        self.last_key_time: Optional[float] = None
        self.line_start_time: Optional[datetime] = None
        self._lock = threading.Lock()
        self._on_event = on_event

        # Key symbols from platform backend
        self.SPECIAL_KEYS = get_backend().get_key_symbols()

        # Window state
        self._current_app_name = ""
        self._current_window_title = ""
        self._current_bundle_id = ""
        self._last_flush_app = ""
        self._last_header_app = ""

    def _get_log_file(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.storage_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"{today}.log"

    def _ensure_app_header(self):
        """Write window header if the active app changed."""
        if self._current_app_name and self._current_app_name != self._last_header_app:
            now = datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

            if self._current_window_title:
                header = f"\n\n\n[{timestamp}] {self._current_app_name} | {self._current_window_title} ({self._current_bundle_id})\n"
            else:
                header = f"\n\n\n[{timestamp}] {self._current_app_name} ({self._current_bundle_id})\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(header)

            self._last_header_app = self._current_app_name

    def _flush_line(self):
        """Write current keyboard line to log file."""
        if self.current_line and self.line_start_time:
            self._ensure_app_header()

            timestamp = self.line_start_time.strftime("%H:%M:%S")
            line = f"[{timestamp}] \u2328\ufe0f {self.current_line}\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)

            if self._on_event:
                self._on_event("keyboard", {"line": self.current_line, "app": self._current_app_name})

            self.current_line = ""
            self.line_start_time = None

    def _update_window_state(self, window_info=None):
        """Update current window state (no log write)."""
        if window_info:
            app_name, window_title, bundle_id = window_info
        else:
            app_name, window_title, bundle_id = get_backend().get_active_window_info()
        self._current_app_name = app_name
        self._current_window_title = window_title
        self._current_bundle_id = bundle_id

    def log_screenshot(self, filename: str, action: str, x: int, y: int,
                       x2: Optional[int] = None, y2: Optional[int] = None,
                       window_info=None):
        """Log screenshot event."""
        with self._lock:
            if window_info:
                self._update_window_state(window_info)
            self._ensure_app_header()

            now = datetime.now()
            timestamp = now.strftime("%H:%M:%S")

            line = f"[{timestamp}] \U0001f4f7 {filename}\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)

            if self._on_event:
                self._on_event("screenshot", {"filename": filename, "action": action, "x": x, "y": y})

    def on_window_activated(self, app_name: str, window_title: str, bundle_id: str):
        """Window activation callback from WindowTracker."""
        with self._lock:
            if app_name != self._current_app_name:
                self._flush_line()

            self._current_app_name = app_name
            self._current_window_title = window_title
            self._current_bundle_id = bundle_id
            self._ensure_app_header()

            if self._on_event:
                self._on_event("window", {"app": app_name, "title": window_title, "bundle_id": bundle_id})

    def log_mic_event(self, event_type: str, detail: str, timestamp: str = None):
        """Log microphone event."""
        with self._lock:
            if timestamp is None:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if event_type == "mic_stop":
                line = f"[{timestamp}] \U0001f3a4 {event_type} {detail}\n"
            else:
                line = f"[{timestamp}] \U0001f3a4 {event_type} | {detail}\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)

            if self._on_event:
                self._on_event("mic", {"event_type": event_type, "detail": detail})

    def on_key_press(self, key):
        """Key press event handler."""
        now = time.time()
        now_dt = datetime.now()

        if key in self.SPECIAL_KEYS:
            char = self.SPECIAL_KEYS[key]
        elif hasattr(key, 'char') and key.char:
            char = key.char
        else:
            char = f'[{key}]'

        with self._lock:
            self._update_window_state()

            window_changed = (self._current_app_name != self._last_flush_app)
            time_gap = self.last_key_time and (now - self.last_key_time) > self.CLUSTER_INTERVAL

            if window_changed or time_gap:
                self._flush_line()

            if not self.line_start_time:
                self.line_start_time = now_dt
                self._last_flush_app = self._current_app_name

            self.current_line += char
            self.last_key_time = now

    def flush(self):
        """Force flush."""
        with self._lock:
            self._flush_line()


class MouseCapture:
    """Mouse activity capture - supports click, double-click, drag."""

    THROTTLE_MS = 100
    DRAG_THRESHOLD = 10
    DOUBLE_CLICK_INTERVAL = 400
    DOUBLE_CLICK_DISTANCE = 5
    WINDOW_BORDER_COLOR = (0, 120, 255)
    WINDOW_BORDER_WIDTH = 3
    IMAGE_FORMAT = "webp"
    IMAGE_QUALITY = 80

    def __init__(self, storage_dir: Path, key_logger: Optional['KeyLogger'] = None):
        self.storage_dir = storage_dir
        self.key_logger = key_logger
        self._lock = threading.Lock()

        self._press_time: float = 0
        self._press_x: int = 0
        self._press_y: int = 0
        self._press_button: str = ""

        self._last_click_time: float = 0
        self._last_click_x: int = 0
        self._last_click_y: int = 0

        self._pending_click_timer: Optional[threading.Timer] = None
        self._pending_click_args: Optional[tuple] = None

        self._last_capture_time: float = 0
        self._active_threads: list[threading.Thread] = []

    def _get_day_dir(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.storage_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _get_window_at_point(self, x: int, y: int) -> tuple[str, str, str]:
        """Get window info at screen coordinates via platform backend."""
        return get_backend().get_window_at_point(x, y)

    def _get_active_window_bounds(self) -> Optional[tuple[int, int, int, int]]:
        """Get the active window bounds via platform backend."""
        return get_backend().get_active_window_bounds()

    def _capture_and_save(self, action: str, button: str,
                          x1: int, y1: int,
                          x2: Optional[int] = None, y2: Optional[int] = None,
                          window_info=None):
        """Take screenshot and save."""
        try:
            window_bounds = self._get_active_window_bounds()

            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screenshot = sct.grab(monitor)
                offset_x, offset_y = monitor["left"], monitor["top"]

            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img_x1 = x1 - offset_x
            img_y1 = y1 - offset_y

            # Draw active window blue border
            if window_bounds:
                win_x, win_y, win_w, win_h = window_bounds
                win_img_x = win_x - offset_x
                win_img_y = win_y - offset_y

                draw = ImageDraw.Draw(img)
                draw.rectangle(
                    [win_img_x, win_img_y, win_img_x + win_w, win_img_y + win_h],
                    outline=self.WINDOW_BORDER_COLOR,
                    width=self.WINDOW_BORDER_WIDTH,
                )

            # Draw drag overlay
            if action == "drag" and x2 is not None and y2 is not None:
                img_x2 = x2 - offset_x
                img_y2 = y2 - offset_y

                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                left = min(img_x1, img_x2)
                top = min(img_y1, img_y2)
                right = max(img_x1, img_x2)
                bottom = max(img_y1, img_y2)

                draw.rectangle(
                    [left, top, right, bottom],
                    fill=(128, 128, 128, 77),
                    outline=(80, 80, 80, 200),
                    width=2,
                )

                img = img.convert("RGBA")
                img = Image.alpha_composite(img, overlay)
                img = img.convert("RGB")

            # Generate filename
            now = datetime.now()
            timestamp = now.strftime("%H%M%S")
            ms = now.strftime("%f")[:3]
            ext = self.IMAGE_FORMAT

            if action == "drag":
                filename = f"drag_{timestamp}_{ms}_{button}_x{x1}_y{y1}_to_x{x2}_y{y2}.{ext}"
            elif action == "dblclick":
                filename = f"dblclick_{timestamp}_{ms}_{button}_x{x1}_y{y1}.{ext}"
            else:
                filename = f"click_{timestamp}_{ms}_{button}_x{x1}_y{y1}.{ext}"

            filepath = self._get_day_dir() / filename
            img.save(filepath, "WEBP", quality=self.IMAGE_QUALITY)

            if self.key_logger:
                self.key_logger.log_screenshot(filename, action, x1, y1, x2, y2,
                                               window_info=window_info)

            print(f"[Screenshot] {filename}")

        except Exception as e:
            print(f"[Error] Screenshot failed: {e}")

    def _distance(self, x1: int, y1: int, x2: int, y2: int) -> float:
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    def _cancel_pending_click(self):
        """Cancel pending click (caller must hold self._lock)."""
        if self._pending_click_timer:
            self._pending_click_timer.cancel()
            self._pending_click_timer = None
            self._pending_click_args = None

    def _fire_pending_click(self):
        """Fire pending click screenshot (called by Timer thread)."""
        with self._lock:
            args = self._pending_click_args
            self._pending_click_timer = None
            self._pending_click_args = None
        if args:
            button_name, x, y, window_info = args
            self._start_capture_thread("click", button_name, x, y,
                                       window_info=window_info)

    def _start_capture_thread(self, action, button_name, x1, y1,
                              x2=None, y2=None, window_info=None):
        """Start screenshot thread."""
        if x2 is not None:
            thread = threading.Thread(
                target=self._capture_and_save,
                args=(action, button_name, x1, y1, x2, y2),
                kwargs={"window_info": window_info},
            )
        else:
            thread = threading.Thread(
                target=self._capture_and_save,
                args=(action, button_name, x1, y1),
                kwargs={"window_info": window_info},
            )
        thread.start()
        with self._lock:
            self._active_threads.append(thread)
            self._active_threads = [t for t in self._active_threads if t.is_alive()]

    def wait_for_pending(self, timeout: float = 2.0):
        """Wait for all screenshot threads to complete."""
        args = None
        with self._lock:
            if self._pending_click_timer:
                self._pending_click_timer.cancel()
                args = self._pending_click_args
                self._pending_click_timer = None
                self._pending_click_args = None
        if args:
            button_name, x, y, window_info = args
            self._start_capture_thread("click", button_name, x, y,
                                       window_info=window_info)
        for thread in self._active_threads:
            thread.join(timeout=timeout)

    def on_click(self, x: float, y: float, button, pressed: bool):
        """Mouse event handler."""
        x, y = int(x), int(y)
        now = time.time() * 1000
        button_name = str(button).split(".")[-1]

        if pressed:
            with self._lock:
                self._press_time = now
                self._press_x = x
                self._press_y = y
                self._press_button = button_name
        else:
            with self._lock:
                if now - self._last_capture_time < self.THROTTLE_MS:
                    return
                self._last_capture_time = now
                press_x = self._press_x
                press_y = self._press_y

            window_info = self._get_window_at_point(x, y)
            drag_distance = self._distance(press_x, press_y, x, y)

            if drag_distance > self.DRAG_THRESHOLD:
                with self._lock:
                    self._cancel_pending_click()
                window_info = self._get_window_at_point(press_x, press_y)
                self._start_capture_thread("drag", button_name,
                                           press_x, press_y, x, y,
                                           window_info=window_info)
            else:
                with self._lock:
                    time_since_last = now - self._last_click_time
                    dist_from_last = self._distance(
                        x, y, self._last_click_x, self._last_click_y
                    )

                    if (time_since_last < self.DOUBLE_CLICK_INTERVAL and
                            dist_from_last < self.DOUBLE_CLICK_DISTANCE):
                        self._cancel_pending_click()
                        self._last_click_time = 0
                        is_dblclick = True
                    else:
                        self._last_click_time = now
                        self._last_click_x = x
                        self._last_click_y = y
                        is_dblclick = False

                if is_dblclick:
                    self._start_capture_thread("dblclick", button_name, x, y,
                                               window_info=window_info)
                else:
                    with self._lock:
                        self._cancel_pending_click()
                        self._pending_click_args = (button_name, x, y, window_info)
                        delay_s = self.DOUBLE_CLICK_INTERVAL / 1000.0
                        self._pending_click_timer = threading.Timer(
                            delay_s, self._fire_pending_click
                        )
                        self._pending_click_timer.daemon = True
                        self._pending_click_timer.start()


class AutoCapture:
    """Main capture controller."""

    def __init__(self, storage_dir: Optional[str] = None, mic_enabled: bool = False,
                 mic_config: Optional[dict] = None, on_event=None):
        if storage_dir:
            self.storage_dir = Path(storage_dir).expanduser()
        else:
            self.storage_dir = Path.home() / "opencapture"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.key_logger = KeyLogger(self.storage_dir, on_event=on_event)
        self.mouse_capture = MouseCapture(self.storage_dir, self.key_logger)
        self.window_tracker = WindowTracker(self.key_logger.on_window_activated)
        self.mic_capture = None

        if mic_enabled:
            from opencapture.mic import create_mic_capture
            self.mic_capture = create_mic_capture(
                storage_dir=self.storage_dir,
                key_logger=self.key_logger,
                mic_config=mic_config,
            )

        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None
        self._running = False

    def start(self):
        """Start all listeners."""
        print(f"[AutoCapture] Starting... Storage: {self.storage_dir}")
        print("[AutoCapture] Press Ctrl+C to stop")

        self._running = True

        self.window_tracker.start()

        self._keyboard_listener = keyboard.Listener(
            on_press=self.key_logger.on_key_press
        )
        self._keyboard_listener.start()

        self._mouse_listener = mouse.Listener(
            on_click=self.mouse_capture.on_click
        )
        self._mouse_listener.start()

        if self.mic_capture:
            self.mic_capture.start()

        print("[AutoCapture] Running...")

    def stop(self):
        """Stop all listeners."""
        print("\n[AutoCapture] Stopping...")

        self._running = False

        self.window_tracker.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

        if self.mic_capture:
            self.mic_capture.stop()

        self.mouse_capture.wait_for_pending()
        self.key_logger.flush()

        print("[AutoCapture] Stopped.")

    @staticmethod
    def _check_accessibility(prompt=False):
        """Check platform accessibility permissions (delegates to backend)."""
        return get_backend().check_accessibility(prompt=prompt)

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self):
        """Run capture (blocking). Checks permissions, starts, and runs event loop."""
        backend = get_backend()

        if not backend.check_accessibility(prompt=False):
            print("[AutoCapture] Requesting Accessibility permission...")
            backend.check_accessibility(prompt=True)
            print("[AutoCapture] Grant access to OpenCapture in System Settings -> Accessibility")

            max_wait = 100 if sys.stdout.isatty() else 40
            print("[AutoCapture] Waiting for permission...")

            granted = False
            for i in range(max_wait):
                time.sleep(3)
                if backend.check_accessibility(prompt=False):
                    granted = True
                    break
                if i % 10 == 9:
                    print("[AutoCapture] Still waiting for permission...")

            if not granted:
                print("[AutoCapture] Permission not granted.")
                sys.exit(1)
            print("[AutoCapture] Accessibility permission granted!")

        self.start()

        try:
            backend.run_event_loop(lambda: self._running)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auto Capture - Keyboard/mouse activity collection")
    parser.add_argument(
        "-d", "--dir",
        help="Storage directory (default: ~/opencapture)",
        default=None,
    )

    args = parser.parse_args()

    capture = AutoCapture(storage_dir=args.dir)
    capture.run()


if __name__ == "__main__":
    main()
