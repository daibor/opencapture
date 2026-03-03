"""
Platform abstraction layer.

Provides a single get_backend() factory that returns the appropriate
PlatformBackend for the current OS. All platform-specific window/permission
logic lives in the backend implementations.
"""

import sys
from typing import Optional

from ._base import PlatformBackend

_backend: Optional[PlatformBackend] = None


def get_backend() -> PlatformBackend:
    """Return the singleton PlatformBackend for the current OS."""
    global _backend
    if _backend is None:
        if sys.platform == "darwin":
            from ._macos import MacOSBackend
            _backend = MacOSBackend()
        elif sys.platform == "win32":
            from ._windows import WindowsBackend
            _backend = WindowsBackend()
        else:
            from ._fallback import FallbackBackend
            _backend = FallbackBackend()
    return _backend


__all__ = ["PlatformBackend", "get_backend"]
