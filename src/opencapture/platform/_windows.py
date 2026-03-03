"""Windows platform backend — Win32 ctypes APIs."""

import ctypes
import ctypes.wintypes
import threading
import time
from typing import Callable, Optional

from ._base import PlatformBackend

# ── Win32 setup ──────────────────────────────────────────

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_psapi = ctypes.windll.psapi

_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_VM_READ = 0x0010
_GA_ROOTOWNER = 3


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _get_process_name(pid: int) -> str:
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
            if name.lower().endswith(".exe"):
                name = name[:-4]
            return name or "Unknown"
        finally:
            _kernel32.CloseHandle(handle)
    except Exception:
        return "Unknown"


class WindowsBackend(PlatformBackend):

    def __init__(self):
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_callback: Optional[Callable] = None
        self._polling = False
        self._current_app = ""
        self._current_title = ""

    # ── Window information ───────────────────────────────────

    def get_active_window_info(self) -> tuple[str, str, str]:
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd:
                return "Unknown", "", "Unknown"

            length = _user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            window_title = buf.value

            pid = ctypes.wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_name = _get_process_name(pid.value)

            return process_name, window_title, process_name
        except Exception:
            return "Unknown", "", "Unknown"

    def get_window_at_point(self, x: int, y: int) -> tuple[str, str, str]:
        try:
            point = ctypes.wintypes.POINT(x, y)
            hwnd = _user32.WindowFromPoint(point)
            if not hwnd:
                return self.get_active_window_info()

            root = _user32.GetAncestor(hwnd, _GA_ROOTOWNER)
            if root:
                hwnd = root

            length = _user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            window_title = buf.value

            pid = ctypes.wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_name = _get_process_name(pid.value)

            return process_name, window_title, process_name
        except Exception:
            return self.get_active_window_info()

    def get_active_window_bounds(self) -> Optional[tuple[int, int, int, int]]:
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

    # ── Window observation ───────────────────────────────────

    def start_window_observer(self, callback: Callable[[str, str, str], None]):
        self._poll_callback = callback
        self._polling = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="window-tracker"
        )
        self._poll_thread.start()

    def _poll_loop(self):
        while self._polling:
            try:
                app_name, window_title, bundle_id = self.get_active_window_info()
                if app_name != self._current_app or window_title != self._current_title:
                    self._current_app = app_name
                    self._current_title = window_title
                    if self._poll_callback:
                        self._poll_callback(app_name, window_title, bundle_id)
            except Exception:
                pass
            time.sleep(0.5)

    def stop_window_observer(self):
        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None
        self._poll_callback = None

    # ── Accessibility / permissions ──────────────────────────

    def check_accessibility(self, prompt: bool = False) -> bool:
        return True  # Windows has no Accessibility permission gate

    # ── Event loop ───────────────────────────────────────────

    def run_event_loop(self, should_run: Callable[[], bool]):
        while should_run():
            time.sleep(0.1)

    # ── Key symbols ──────────────────────────────────────────

    def get_key_symbols(self) -> dict:
        from pynput import keyboard
        symbols = super().get_key_symbols()
        symbols.update({
            keyboard.Key.ctrl: 'Ctrl+',
            keyboard.Key.ctrl_l: 'Ctrl+',
            keyboard.Key.ctrl_r: 'Ctrl+',
            keyboard.Key.alt: 'Alt+',
            keyboard.Key.alt_l: 'Alt+',
            keyboard.Key.alt_r: 'Alt+',
            keyboard.Key.alt_gr: 'AltGr+',
            keyboard.Key.cmd: 'Win+',
            keyboard.Key.cmd_l: 'Win+',
            keyboard.Key.cmd_r: 'Win+',
            keyboard.Key.shift: 'Shift+',
            keyboard.Key.shift_l: 'Shift+',
            keyboard.Key.shift_r: 'Shift+',
            keyboard.Key.enter: 'Enter',
            keyboard.Key.tab: 'Tab',
            keyboard.Key.backspace: 'Bksp',
            keyboard.Key.delete: 'Del',
            keyboard.Key.esc: 'Esc',
            keyboard.Key.caps_lock: 'CapsLock',
        })
        return symbols
