"""
OpenCapture GUI — cross-platform system tray application.

Dispatches to the appropriate backend:
    macOS:         Native PyObjC (NSStatusBar + NSWindow)
    Windows/Linux: pystray + tkinter

Launch:
    opencapture gui          # via CLI subcommand
    opencapture-gui          # standalone entry point
"""

from .config import init_config
from .gui import create_app


def main():
    """Launch the system tray GUI."""
    config = init_config()
    app = create_app(config)
    app.run()
