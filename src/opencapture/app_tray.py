"""
OpenCapture cross-platform system tray GUI using pystray.

Works on macOS and Windows. Provides a system tray icon with
Start/Stop toggle, status display, analysis trigger, and quit.

The native macOS PyObjC GUI (app.py) remains the primary macOS option.
This module provides an alternative that works on both platforms.

Launch:
    opencapture gui --tray     # force cross-platform tray
    opencapture gui            # native on macOS, tray on Windows
"""

import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import pystray
from PIL import Image, ImageDraw

from .config import Config, init_config
from .engine import CaptureEngine, AnalysisEngine


def _create_icon_image(recording: bool = False) -> Image.Image:
    """Create a simple tray icon image.

    Green circle when recording, gray circle when stopped.
    """
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if recording:
        # Green filled circle with dark border
        draw.ellipse([4, 4, size - 4, size - 4], fill=(34, 197, 94), outline=(22, 163, 74), width=2)
    else:
        # Gray filled circle with dark border
        draw.ellipse([4, 4, size - 4, size - 4], fill=(156, 163, 175), outline=(107, 114, 128), width=2)

    return img


class TrayApp:
    """Cross-platform system tray application for OpenCapture."""

    def __init__(self, config: Config):
        self.config = config
        self.capture_engine = CaptureEngine(config)
        self.analysis_engine = AnalysisEngine(config)
        self._icon: Optional[pystray.Icon] = None
        self._status_text = "No data yet"
        self._status_timer: Optional[threading.Timer] = None

    def _get_menu(self) -> pystray.Menu:
        """Build the tray menu."""
        is_running = self.capture_engine.is_running

        return pystray.Menu(
            pystray.MenuItem(
                "Stop Capture" if is_running else "Start Capture",
                self._toggle_capture,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Analyze Today",
                self._analyze_today,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: self._status_text,
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _toggle_capture(self, icon, item):
        """Start or stop capture."""
        if self.capture_engine.is_running:
            self.capture_engine.stop()
        else:
            if sys.platform == "darwin":
                if not CaptureEngine.check_accessibility(prompt=False):
                    CaptureEngine.check_accessibility(prompt=True)
                    print("[Tray] Grant Accessibility permission, then try again.")
                    return

            error = self.capture_engine.start()
            if error:
                print(f"[Tray] Failed to start capture: {error}")
                return

        self._update_icon()
        self._update_status()

    def _analyze_today(self, icon, item):
        """Trigger analysis of today's data."""
        self._status_text = "Analyzing..."
        self._update_icon()

        def on_result(result):
            try:
                if isinstance(result, dict) and "error" in result:
                    self._status_text = f"Error: {result['error']}"
                elif isinstance(result, dict):
                    images = result.get("images_analyzed", 0)
                    audios = result.get("audios_transcribed", 0)
                    logs = result.get("logs_analyzed", 0)
                    self._status_text = f"Done: {images} img, {audios} audio, {logs} logs"
                else:
                    self._status_text = str(result)
            except Exception as e:
                self._status_text = f"Error: {e}"
            self._update_icon()

        provider = self.config.get_default_provider()
        self.analysis_engine.analyze_today(provider=provider, callback=on_result)

    def _quit(self, icon, item):
        """Quit the application."""
        self._stop_status_timer()
        if self.capture_engine.is_running:
            self.capture_engine.stop()
        self.analysis_engine.stop()
        icon.stop()

    def _update_icon(self):
        """Update tray icon and menu."""
        if self._icon:
            self._icon.icon = _create_icon_image(self.capture_engine.is_running)
            self._icon.menu = self._get_menu()

    def _update_status(self):
        """Update the status text from capture engine stats."""
        status = self.capture_engine.get_status()
        parts = []
        if status["screenshots"]:
            parts.append(f"{status['screenshots']} screenshots")
        if status["recordings"]:
            parts.append(f"{status['recordings']} recordings")

        if parts:
            text = ", ".join(parts)
        else:
            text = "No data yet"

        if status["running"]:
            text = f"Running - {text}"

        self._status_text = text

    def _status_timer_tick(self):
        """Periodic status update."""
        if self._icon:
            self._update_status()
            self._update_icon()
            self._start_status_timer()

    def _start_status_timer(self):
        """Start periodic status update timer."""
        self._status_timer = threading.Timer(5.0, self._status_timer_tick)
        self._status_timer.daemon = True
        self._status_timer.start()

    def _stop_status_timer(self):
        """Stop the status timer."""
        if self._status_timer:
            self._status_timer.cancel()
            self._status_timer = None

    def run(self):
        """Run the tray application (blocking)."""
        from .onboarding import is_first_run, mark_setup_complete

        self.analysis_engine.start()
        self._start_status_timer()

        self._icon = pystray.Icon(
            "OpenCapture",
            icon=_create_icon_image(False),
            title="OpenCapture",
            menu=self._get_menu(),
        )

        if is_first_run():
            # Show a notification after the icon is set up
            def _on_setup(icon):
                icon.notify(
                    "OpenCapture is ready. Click the tray icon to start capture.\n"
                    "All data stays on your machine.",
                    "Welcome to OpenCapture"
                )
                mark_setup_complete()

            self._icon.run(setup=_on_setup)
        else:
            # pystray.Icon.run() blocks until icon.stop() is called
            self._icon.run()


def main():
    """Launch the cross-platform tray GUI."""
    config = init_config()
    app = TrayApp(config)
    app.run()
