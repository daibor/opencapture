"""
OpenCapture GUI — cross-platform system tray application.

Platform backends:
    macOS:         PyObjC (native NSStatusBar + NSWindow)
    Windows/Linux: pystray + tkinter
"""

import sys

from .base import TrayAppBase


def create_app(config) -> TrayAppBase:
    """Create the platform-appropriate tray application."""
    if sys.platform == "darwin":
        from .macos import MacOSTrayApp
        return MacOSTrayApp(config)
    else:
        from .generic import GenericTrayApp
        return GenericTrayApp(config)


__all__ = ["TrayAppBase", "create_app"]
