"""Fallback platform backend for unsupported platforms (Linux, etc.)."""

import threading
import time
from typing import Callable, Optional

from ._base import PlatformBackend


class FallbackBackend(PlatformBackend):
    """Minimal backend — window info unavailable, capture still works."""

    def __init__(self):
        self._poll_thread: Optional[threading.Thread] = None
        self._polling = False

    def get_active_window_info(self) -> tuple[str, str, str]:
        return "Unknown", "", "Unknown"

    def get_window_at_point(self, x: int, y: int) -> tuple[str, str, str]:
        return "Unknown", "", "Unknown"

    def get_active_window_bounds(self) -> Optional[tuple[int, int, int, int]]:
        return None

    def start_window_observer(self, callback: Callable[[str, str, str], None]):
        pass  # No window change events on unsupported platforms

    def stop_window_observer(self):
        pass

    def check_accessibility(self, prompt: bool = False) -> bool:
        return True

    def run_event_loop(self, should_run: Callable[[], bool]):
        while should_run():
            time.sleep(0.1)
