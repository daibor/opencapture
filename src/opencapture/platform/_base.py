"""
PlatformBackend — abstract interface for all platform-specific operations.

Each platform (macOS, Windows, Linux) implements this interface.
Core modules (auto_capture, engine) depend only on this ABC.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional


class PlatformBackend(ABC):
    """Abstract platform backend for window management and system integration."""

    # ── Window information ───────────────────────────────────

    @abstractmethod
    def get_active_window_info(self) -> tuple[str, str, str]:
        """Return (app_name, window_title, bundle_id) of the frontmost window."""

    @abstractmethod
    def get_window_at_point(self, x: int, y: int) -> tuple[str, str, str]:
        """Return (app_name, window_title, bundle_id) of the window at screen coordinates."""

    @abstractmethod
    def get_active_window_bounds(self) -> Optional[tuple[int, int, int, int]]:
        """Return (x, y, width, height) of the frontmost window, or None."""

    # ── Window observation ───────────────────────────────────

    @abstractmethod
    def start_window_observer(self, callback: Callable[[str, str, str], None]):
        """Start watching for window activation changes.

        Args:
            callback: Called with (app_name, window_title, bundle_id) on change.
        """

    @abstractmethod
    def stop_window_observer(self):
        """Stop watching for window activation changes."""

    # ── Accessibility / permissions ──────────────────────────

    @abstractmethod
    def check_accessibility(self, prompt: bool = False) -> bool:
        """Check if the process has input monitoring permissions.

        Args:
            prompt: If True, trigger native permission dialog (macOS only).
        Returns:
            True if permission is granted.
        """

    # ── Event loop ───────────────────────────────────────────

    @abstractmethod
    def run_event_loop(self, should_run: Callable[[], bool]):
        """Block the calling thread with a platform event loop.

        On macOS this pumps NSRunLoop (required for notifications).
        On Windows/Linux this is a simple sleep loop.

        Args:
            should_run: Callable that returns False to break the loop.
        """

    # ── Key symbols ──────────────────────────────────────────

    def get_key_symbols(self) -> dict:
        """Return platform-appropriate key symbol mapping.

        Override per-platform. Default returns macOS-style Unicode symbols.
        """
        from pynput import keyboard
        return {
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
            keyboard.Key.f1: 'F1', keyboard.Key.f2: 'F2',
            keyboard.Key.f3: 'F3', keyboard.Key.f4: 'F4',
            keyboard.Key.f5: 'F5', keyboard.Key.f6: 'F6',
            keyboard.Key.f7: 'F7', keyboard.Key.f8: 'F8',
            keyboard.Key.f9: 'F9', keyboard.Key.f10: 'F10',
            keyboard.Key.f11: 'F11', keyboard.Key.f12: 'F12',
        }
