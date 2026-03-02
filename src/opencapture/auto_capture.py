#!/usr/bin/env python3
"""
Auto Capture - Cross-platform keyboard and mouse activity collection tool.

Supports macOS (primary, with native AppKit/Quartz integration) and
Windows (using Win32 ctypes APIs). Linux has basic fallback support.
"""

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from pynput import keyboard, mouse
from PIL import Image, ImageDraw
import mss

# ── Platform-specific imports ──────────────────────────────

_IS_MACOS = sys.platform == "darwin"
_IS_WINDOWS = sys.platform == "win32"

if _IS_MACOS:
    import AppKit
    import Quartz

if _IS_WINDOWS:
    import ctypes
    import ctypes.wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _psapi = ctypes.windll.psapi

    # Win32 constants
    _PROCESS_QUERY_INFORMATION = 0x0400
    _PROCESS_VM_READ = 0x0010
    _GW_OWNER = 4
    _GA_ROOTOWNER = 3
    _DWMWA_CLOAKED = 14

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]


# ── Platform-specific window helpers ──────────────────────


def _get_active_window_info_macos() -> tuple[str, str, str]:
    """Get (app_name, window_title, bundle_id) on macOS."""
    try:
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()
        app_name = active_app.localizedName() or "Unknown"
        bundle_id = active_app.bundleIdentifier() or "Unknown"
        pid = active_app.processIdentifier()
        window_title = _get_window_title_macos(pid)
        return app_name, window_title, bundle_id
    except Exception:
        return "Unknown", "", "Unknown"


def _get_window_title_macos(pid: int) -> str:
    """Get window title via Accessibility API on macOS."""
    try:
        app_ref = Quartz.AXUIElementCreateApplication(pid)
        error, focused_window = Quartz.AXUIElementCopyAttributeValue(
            app_ref, Quartz.kAXFocusedWindowAttribute, None
        )
        if error == 0 and focused_window:
            error, title = Quartz.AXUIElementCopyAttributeValue(
                focused_window, Quartz.kAXTitleAttribute, None
            )
            if error == 0 and title:
                return str(title)
        error, windows = Quartz.AXUIElementCopyAttributeValue(
            app_ref, Quartz.kAXWindowsAttribute, None
        )
        if error == 0 and windows and len(windows) > 0:
            error, title = Quartz.AXUIElementCopyAttributeValue(
                windows[0], Quartz.kAXTitleAttribute, None
            )
            if error == 0 and title:
                return str(title)
        return ""
    except Exception:
        return ""


def _get_active_window_info_windows() -> tuple[str, str, str]:
    """Get (app_name, window_title, process_name) on Windows."""
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return "Unknown", "", "Unknown"

        # Window title
        length = _user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        window_title = buf.value

        # Process name via PID
        pid = ctypes.wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = _get_process_name_windows(pid.value)

        return process_name, window_title, process_name
    except Exception:
        return "Unknown", "", "Unknown"


def _get_process_name_windows(pid: int) -> str:
    """Get process executable name from PID on Windows."""
    try:
        handle = _kernel32.OpenProcess(
            _PROCESS_QUERY_INFORMATION | _PROCESS_VM_READ, False, pid
        )
        if not handle:
            return "Unknown"
        try:
            buf = ctypes.create_unicode_buffer(260)
            _psapi.GetModuleBaseNameW(handle, None, buf, 260)
            name = buf.value
            # Strip .exe suffix for cleaner display
            if name.lower().endswith(".exe"):
                name = name[:-4]
            return name or "Unknown"
        finally:
            _kernel32.CloseHandle(handle)
    except Exception:
        return "Unknown"


def _get_window_at_point_windows(x: int, y: int) -> tuple[str, str, str]:
    """Get window info at screen coordinates on Windows."""
    try:
        point = ctypes.wintypes.POINT(x, y)
        hwnd = _user32.WindowFromPoint(point)
        if not hwnd:
            return _get_active_window_info_windows()

        # Walk up to the root owner window
        root = _user32.GetAncestor(hwnd, _GA_ROOTOWNER)
        if root:
            hwnd = root

        # Window title
        length = _user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        window_title = buf.value

        # Process name
        pid = ctypes.wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = _get_process_name_windows(pid.value)

        return process_name, window_title, process_name
    except Exception:
        return _get_active_window_info_windows()


def _get_active_window_bounds_windows() -> Optional[tuple[int, int, int, int]]:
    """Get (x, y, width, height) of the foreground window on Windows."""
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = _RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 100 or h < 100:
            return None
        return (rect.left, rect.top, w, h)
    except Exception:
        return None


def _get_active_window_info_fallback() -> tuple[str, str, str]:
    """Fallback for unsupported platforms."""
    return "Unknown", "", "Unknown"


# Dispatch helpers based on platform
def _platform_get_active_window_info() -> tuple[str, str, str]:
    if _IS_MACOS:
        return _get_active_window_info_macos()
    elif _IS_WINDOWS:
        return _get_active_window_info_windows()
    return _get_active_window_info_fallback()


# ── WindowTracker ─────────────────────────────────────────


class WindowTracker:
    """Track active window changes across platforms."""

    def __init__(self, on_window_change):
        self.on_window_change = on_window_change
        self.current_app_name: Optional[str] = None
        self.current_window_title: Optional[str] = None
        self.current_bundle_id: Optional[str] = None
        self._running = False
        self._observer = None  # macOS NSNotification observer
        self._poll_thread = None  # Windows/Linux polling thread

    def _get_active_window_info(self) -> tuple[str, str, str]:
        return _platform_get_active_window_info()

    def _handle_app_activation(self, notification=None):
        """Handle app activation (macOS notification or polling result)."""
        app_name, window_title, bundle_id = self._get_active_window_info()
        self.current_app_name = app_name
        self.current_window_title = window_title
        self.current_bundle_id = bundle_id
        self.on_window_change(app_name, window_title, bundle_id)

    def _poll_loop(self):
        """Polling loop for window changes (Windows/Linux)."""
        while self._running:
            try:
                app_name, window_title, bundle_id = self._get_active_window_info()
                if app_name != self.current_app_name or window_title != self.current_window_title:
                    self.current_app_name = app_name
                    self.current_window_title = window_title
                    self.current_bundle_id = bundle_id
                    self.on_window_change(app_name, window_title, bundle_id)
            except Exception:
                pass
            time.sleep(0.5)

    def start(self):
        """Start window change monitoring."""
        self._running = True

        # Get initial window info
        app_name, window_title, bundle_id = self._get_active_window_info()
        self.current_app_name = app_name
        self.current_window_title = window_title
        self.current_bundle_id = bundle_id
        self.on_window_change(app_name, window_title, bundle_id)

        if _IS_MACOS:
            # Use NSWorkspace notification for efficient event-driven tracking
            nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
            self._observer = nc.addObserverForName_object_queue_usingBlock_(
                AppKit.NSWorkspaceDidActivateApplicationNotification,
                None,
                AppKit.NSOperationQueue.mainQueue(),
                self._handle_app_activation,
            )
        else:
            # Use polling on Windows/Linux
            self._poll_thread = threading.Thread(
                target=self._poll_loop, daemon=True, name="window-tracker"
            )
            self._poll_thread.start()

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if _IS_MACOS and self._observer:
            nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
            nc.removeObserver_(self._observer)
            self._observer = None
        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None


class KeyLogger:
    """Keyboard logger with time clustering and window grouping."""

    CLUSTER_INTERVAL = 20  # 20s clustering interval

    # Current window state
    _current_app_name: str = ""
    _current_window_title: str = ""
    _current_bundle_id: str = ""

    # Special key mapping (macOS keyboard symbols)
    SPECIAL_KEYS = {
        keyboard.Key.enter: '\u21a9',
        keyboard.Key.tab: '\u21e5',
        keyboard.Key.space: ' ',
        keyboard.Key.backspace: '\u232b',
        keyboard.Key.delete: '\u2326',
        keyboard.Key.esc: '\u238b',
        keyboard.Key.shift: '\u21e7',
        keyboard.Key.shift_l: '\u21e7',
        keyboard.Key.shift_r: '\u21e7',
        keyboard.Key.ctrl: '\u2303',
        keyboard.Key.ctrl_l: '\u2303',
        keyboard.Key.ctrl_r: '\u2303',
        keyboard.Key.alt: '\u2325',
        keyboard.Key.alt_l: '\u2325',
        keyboard.Key.alt_r: '\u2325',
        keyboard.Key.alt_gr: '\u2325',
        keyboard.Key.cmd: '\u2318',
        keyboard.Key.cmd_l: '\u2318',
        keyboard.Key.cmd_r: '\u2318',
        keyboard.Key.caps_lock: '\u21ea',
        keyboard.Key.up: '\u2191',
        keyboard.Key.down: '\u2193',
        keyboard.Key.left: '\u2190',
        keyboard.Key.right: '\u2192',
        keyboard.Key.home: '\u2196',
        keyboard.Key.end: '\u2198',
        keyboard.Key.page_up: '\u21de',
        keyboard.Key.page_down: '\u21df',
        keyboard.Key.f1: 'F1',
        keyboard.Key.f2: 'F2',
        keyboard.Key.f3: 'F3',
        keyboard.Key.f4: 'F4',
        keyboard.Key.f5: 'F5',
        keyboard.Key.f6: 'F6',
        keyboard.Key.f7: 'F7',
        keyboard.Key.f8: 'F8',
        keyboard.Key.f9: 'F9',
        keyboard.Key.f10: 'F10',
        keyboard.Key.f11: 'F11',
        keyboard.Key.f12: 'F12',
    }

    def __init__(self, storage_dir: Path, on_event=None):
        self.storage_dir = storage_dir
        self.current_line = ""
        self.last_key_time: Optional[float] = None
        self.line_start_time: Optional[datetime] = None
        self._lock = threading.Lock()
        self._on_event = on_event

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

    def _get_active_window_info(self) -> tuple[str, str, str]:
        return _platform_get_active_window_info()

    def _update_window_state(self, window_info=None):
        """Update current window state (no log write)."""
        if window_info:
            app_name, window_title, bundle_id = window_info
        else:
            app_name, window_title, bundle_id = self._get_active_window_info()
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

            if action == "drag" and x2 is not None:
                line = f"[{timestamp}] \U0001f4f7 {action} ({x},{y})->({x2},{y2}) {filename}\n"
            else:
                line = f"[{timestamp}] \U0001f4f7 {action} ({x},{y}) {filename}\n"

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
        """Get window info at screen coordinates."""
        if _IS_MACOS:
            return self._get_window_at_point_macos(x, y)
        elif _IS_WINDOWS:
            return _get_window_at_point_windows(x, y)
        return _get_active_window_info_fallback()

    def _get_window_at_point_macos(self, x: int, y: int) -> tuple[str, str, str]:
        """macOS: use CGWindowListCopyWindowInfo to find window at point."""
        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
            )
            if not window_list:
                return "Unknown", "", "Unknown"

            for window in window_list:
                bounds = window.get(Quartz.kCGWindowBounds)
                if not bounds:
                    continue

                wx = int(bounds.get("X", 0))
                wy = int(bounds.get("Y", 0))
                ww = int(bounds.get("Width", 0))
                wh = int(bounds.get("Height", 0))

                layer = window.get(Quartz.kCGWindowLayer, -1)
                if layer != 0:
                    continue
                if ww < 50 or wh < 50:
                    continue

                if wx <= x <= wx + ww and wy <= y <= wy + wh:
                    pid = window.get(Quartz.kCGWindowOwnerPID, 0)
                    owner_name = window.get(Quartz.kCGWindowOwnerName, "Unknown")
                    window_name = window.get(Quartz.kCGWindowName, "") or ""

                    bundle_id = "Unknown"
                    try:
                        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
                        if app:
                            bundle_id = app.bundleIdentifier() or "Unknown"
                            owner_name = app.localizedName() or owner_name
                    except Exception:
                        pass

                    return owner_name, window_name, bundle_id

            # Fallback to frontmost app
            try:
                workspace = AppKit.NSWorkspace.sharedWorkspace()
                active_app = workspace.frontmostApplication()
                app_name = active_app.localizedName() or "Unknown"
                bundle_id = active_app.bundleIdentifier() or "Unknown"
                return app_name, "", bundle_id
            except Exception:
                pass
        except Exception:
            pass
        return "Unknown", "", "Unknown"

    def _get_active_window_bounds(self) -> Optional[tuple[int, int, int, int]]:
        """Get the active window bounds (x, y, width, height)."""
        if _IS_MACOS:
            return self._get_active_window_bounds_macos()
        elif _IS_WINDOWS:
            return _get_active_window_bounds_windows()
        return None

    def _get_active_window_bounds_macos(self) -> Optional[tuple[int, int, int, int]]:
        """macOS: get active window bounds via CGWindowList."""
        try:
            workspace = AppKit.NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()
            pid = active_app.processIdentifier()

            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
            )

            for window in window_list:
                if window.get(Quartz.kCGWindowOwnerPID) == pid:
                    bounds = window.get(Quartz.kCGWindowBounds)
                    if not bounds:
                        continue
                    width = int(bounds.get("Width", 0))
                    height = int(bounds.get("Height", 0))
                    if width < 100 or height < 100:
                        continue
                    x = int(bounds.get("X", 0))
                    y = int(bounds.get("Y", 0))
                    return (x, y, width, height)
            return None
        except Exception as e:
            print(f"[Warning] Failed to get window bounds: {e}")
            return None

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
            try:
                from opencapture.mic_capture import MicrophoneCapture
                cfg = mic_config or {}
                self.mic_capture = MicrophoneCapture(
                    storage_dir=self.storage_dir,
                    key_logger=self.key_logger,
                    sample_rate=cfg.get("mic_sample_rate", 16000),
                    channels=cfg.get("mic_channels", 1),
                    min_duration_ms=cfg.get("mic_min_duration_ms", cfg.get("mic_start_debounce_ms", 500)),
                    stop_debounce_ms=cfg.get("mic_stop_debounce_ms", 300),
                )
            except ImportError as e:
                print(f"[AutoCapture] Mic capture unavailable (missing dependency): {e}")
            except Exception as e:
                print(f"[AutoCapture] Mic capture init failed: {e}")

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
        """Check platform accessibility permissions.

        On macOS: checks Accessibility permission via AXIsProcessTrusted.
        On Windows: always returns True (no special permission needed).

        Args:
            prompt: If True, trigger macOS native permission dialog.
        Returns True if granted.
        """
        if sys.platform != 'darwin':
            return True
        try:
            import ctypes as _ct
            lib = _ct.cdll.LoadLibrary(
                '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
            )
            if prompt:
                cf = _ct.cdll.LoadLibrary(
                    '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
                )
                kAXTrustedCheckOptionPrompt = _ct.c_void_p.in_dll(
                    lib, 'kAXTrustedCheckOptionPrompt'
                )
                kCFBooleanTrue = _ct.c_void_p.in_dll(cf, 'kCFBooleanTrue')

                cf.CFDictionaryCreate.restype = _ct.c_void_p
                cf.CFDictionaryCreate.argtypes = [
                    _ct.c_void_p, _ct.POINTER(_ct.c_void_p),
                    _ct.POINTER(_ct.c_void_p), _ct.c_long,
                    _ct.c_void_p, _ct.c_void_p,
                ]
                keys = (_ct.c_void_p * 1)(kAXTrustedCheckOptionPrompt)
                values = (_ct.c_void_p * 1)(kCFBooleanTrue)
                options = cf.CFDictionaryCreate(None, keys, values, 1, None, None)

                lib.AXIsProcessTrustedWithOptions.restype = _ct.c_bool
                lib.AXIsProcessTrustedWithOptions.argtypes = [_ct.c_void_p]
                result = lib.AXIsProcessTrustedWithOptions(options)
                cf.CFRelease.argtypes = [_ct.c_void_p]
                cf.CFRelease(options)
                return result
            else:
                lib.AXIsProcessTrusted.restype = _ct.c_bool
                return lib.AXIsProcessTrusted()
        except Exception:
            return True  # Can't check, assume OK

    def run(self):
        """Run capture (blocking)."""
        if _IS_MACOS:
            if not self._check_accessibility(prompt=False):
                print("[AutoCapture] Requesting Accessibility permission...")
                self._check_accessibility(prompt=True)
                print("[AutoCapture] Grant access to OpenCapture in System Settings -> Accessibility")

                max_wait = 100 if sys.stdout.isatty() else 40
                print("[AutoCapture] Waiting for permission...")

                granted = False
                for i in range(max_wait):
                    time.sleep(3)
                    if self._check_accessibility(prompt=False):
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
            if _IS_MACOS:
                # Use NSRunLoop for macOS notification dispatch
                run_loop = AppKit.NSRunLoop.currentRunLoop()
                while self._running:
                    until = AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.1)
                    run_loop.runUntilDate_(until)
            else:
                # Simple sleep loop for Windows/Linux
                while self._running:
                    time.sleep(0.1)
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
