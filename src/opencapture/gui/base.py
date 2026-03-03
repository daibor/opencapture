"""
TrayAppBase — shared business logic for all GUI backends.

Subclasses implement the abstract UI methods; this class provides
the capture/analysis orchestration that is identical across platforms.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..engine import CaptureEngine, AnalysisEngine


class TrayAppBase(ABC):
    """Abstract system tray application with shared business logic."""

    def __init__(self, config: Config):
        self.config = config
        self.capture_engine = CaptureEngine(config)
        self.analysis_engine = AnalysisEngine(config)

    # ── Business logic (shared) ─────────────────────────────

    def toggle_capture(self):
        """Toggle capture on/off.

        Calls platform UI hooks for permission checks, recording
        indicator updates, and error alerts.
        """
        if self.capture_engine.is_running:
            self.capture_engine.stop()
            self.on_recording_changed(False)
            self.refresh_status()
        else:
            if not self.check_capture_permissions():
                return

            error = self.capture_engine.start()
            if error:
                self.show_alert("Failed to Start Capture", error)
                return
            self.on_recording_changed(True)
            self.refresh_status()

    def request_analysis(self):
        """Start async analysis of today's data."""
        self.on_analysis_started()
        provider = self.config.get_default_provider()
        self.analysis_engine.analyze_today(
            provider=provider,
            callback=self._handle_analysis_result,
        )

    def _handle_analysis_result(self, result):
        """Process analysis result dict and forward to UI."""
        try:
            if isinstance(result, dict) and "error" in result:
                msg = f"Error: {result['error']}"
            elif isinstance(result, dict):
                images = result.get("images_analyzed", 0)
                audios = result.get("audios_transcribed", 0)
                logs = result.get("logs_analyzed", 0)
                msg = f"Done: {images} images, {audios} audios, {logs} logs analyzed"
            else:
                msg = str(result)
        except Exception as e:
            msg = f"Error: {e}"

        self.on_analysis_complete(msg)

    def get_status_text(self) -> str:
        """Build status line string from engine state."""
        status = self.capture_engine.get_status()
        parts = []
        if status["screenshots"]:
            parts.append(f"{status['screenshots']} screenshots")
        if status["recordings"]:
            parts.append(f"{status['recordings']} recordings")
        text = ", ".join(parts) if parts else "No data yet"

        if status["running"]:
            text = f"Running — {text}"
        return text

    def get_log_path(self) -> Path:
        """Return path to today's log file."""
        data_dir = Path(
            self.config.get(
                "capture.output_dir", str(Path.home() / "opencapture")
            )
        ).expanduser()
        today = datetime.now().strftime("%Y-%m-%d")
        return data_dir / today / f"{today}.log"

    def shutdown(self):
        """Clean shutdown of both engines."""
        if self.capture_engine.is_running:
            self.capture_engine.stop()
        self.analysis_engine.stop()

    # ── Abstract UI methods (platform-specific) ─────────────

    @abstractmethod
    def run(self):
        """Start the application event loop (blocks)."""

    @abstractmethod
    def on_recording_changed(self, recording: bool):
        """Update UI to reflect recording state change."""

    @abstractmethod
    def on_analysis_started(self):
        """Update UI when analysis begins (e.g. disable button, show spinner)."""

    @abstractmethod
    def on_analysis_complete(self, message: str):
        """Update UI with analysis result (called from background thread)."""

    @abstractmethod
    def show_alert(self, title: str, message: str):
        """Show a modal alert/notification."""

    @abstractmethod
    def refresh_status(self):
        """Refresh the status line in the tray menu."""

    def check_capture_permissions(self) -> bool:
        """Check platform permissions before starting capture.

        Returns True if capture can proceed. Override for platforms
        that need permission prompts (e.g. macOS Accessibility).
        Default: always returns True.
        """
        return True
