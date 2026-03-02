"""
Engine layer — CaptureEngine and AnalysisEngine.

Sits between core components (auto_capture, analyzer) and frontends (CLI, GUI).
Provides lifecycle management, event dispatch, and async analysis.
"""

import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .config import Config


class CaptureEngine:
    """Manages capture lifecycle and dispatches events to subscribers.

    On macOS, the frontend must pump the NSRunLoop on the main thread
    (e.g. via NSApplication.run()). On Windows/Linux, no special
    event loop is needed. Events fire from capture threads; frontends
    must dispatch to their own main thread if needed.
    """

    def __init__(self, config: Config):
        self._config = config
        self._capture = None  # AutoCapture instance
        self._subscribers: list[tuple[str, Callable]] = []
        self._running = False

    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to capture events.

        Args:
            event_type: One of 'keyboard', 'screenshot', 'window', 'mic',
                        'status', or '*' for all events.
            callback: Called with (event_type: str, data: dict).
        """
        self._subscribers.append((event_type, callback))

    def _emit(self, event_type: str, data: dict):
        """Dispatch event to matching subscribers."""
        for sub_type, callback in self._subscribers:
            if sub_type == "*" or sub_type == event_type:
                try:
                    callback(event_type, data)
                except Exception:
                    pass  # Don't let subscriber errors crash capture

    def start(self):
        """Create AutoCapture with on_event wiring and start listeners.

        On macOS, the caller must be pumping the NSRunLoop on the main
        thread (e.g. via NSApplication.run()). On other platforms, no
        special event loop is needed.

        Returns error message string on failure, None on success.
        """
        if self._running:
            return None

        from .auto_capture import AutoCapture

        capture_config = self._config.get_capture_config()
        try:
            self._capture = AutoCapture(
                storage_dir=self._config.get("capture.output_dir"),
                mic_enabled=capture_config.get("mic_enabled", False),
                mic_config=capture_config,
                on_event=self._emit,
            )
            self._capture.start()
        except Exception as e:
            self._capture = None
            self._emit("status", {"state": "error", "error": str(e)})
            return str(e)

        self._running = True
        self._emit("status", {"state": "started"})
        return None

    def stop(self):
        """Stop capture and emit status event."""
        if not self._running:
            return

        self._running = False
        if self._capture:
            try:
                self._capture.stop()
            except Exception:
                pass
            self._capture = None
        self._emit("status", {"state": "stopped"})

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict:
        """Return today's stats: screenshot count, log size, recording count."""
        output_dir = Path(
            self._config.get("capture.output_dir", str(Path.home() / "opencapture"))
        ).expanduser()
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = output_dir / today

        result = {
            "running": self._running,
            "date": today,
            "data_dir": str(output_dir),
        }

        if today_dir.exists():
            result["screenshots"] = len(list(today_dir.glob("*.webp")))
            result["logs"] = len(list(today_dir.glob("*.log")))
            result["recordings"] = len(list(today_dir.glob("*.wav")))
        else:
            result["screenshots"] = 0
            result["logs"] = 0
            result["recordings"] = 0

        return result

    @staticmethod
    def check_accessibility(prompt=False) -> bool:
        """Check platform accessibility permission.

        On macOS: checks Accessibility permission via AXIsProcessTrusted.
        On other platforms: always returns True.

        Args:
            prompt: If True, trigger macOS native permission dialog.
        """
        from .auto_capture import AutoCapture
        return AutoCapture._check_accessibility(prompt=prompt)


class AnalysisEngine:
    """Runs analysis tasks in a background asyncio event loop.

    Callbacks are invoked from the asyncio thread; frontends must
    dispatch to their own main thread if needed.
    """

    def __init__(self, config: Config):
        self._config = config
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start background asyncio event loop thread."""
        if self._thread and self._thread.is_alive():
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="AnalysisEngine"
        )
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def stop(self):
        """Stop the event loop and thread."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        if self._loop:
            self._loop.close()
            self._loop = None

    def _submit(self, coro_func, callback=None):
        """Submit an async task to the background loop."""
        if not self._loop or not self._loop.is_running():
            if callback:
                callback({"error": "AnalysisEngine not running"})
            return

        async def _wrapper():
            try:
                result = await coro_func()
                if callback:
                    callback(result)
            except Exception as e:
                if callback:
                    callback({"error": str(e)})

        asyncio.run_coroutine_threadsafe(_wrapper(), self._loop)

    def analyze_today(self, provider=None, callback=None, timeout=120):
        """Submit analyze_day task to background loop.

        Args:
            provider: LLM provider name (or None for default).
            callback: Called with results dict when complete.
            timeout: Max seconds before giving up (default 120).
        """
        async def _run():
            from .analyzer import Analyzer
            analyzer = Analyzer(self._config)
            try:
                date_str = datetime.now().strftime("%Y-%m-%d")
                return await asyncio.wait_for(
                    analyzer.analyze_day(
                        date_str,
                        generate_reports=True,
                        provider=provider,
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                return {"error": f"Analysis timed out after {timeout}s. Is your LLM provider running?"}
            finally:
                await analyzer.close()

        self._submit(_run, callback)

    def analyze_image(self, path, provider=None, callback=None):
        """Submit single image analysis.

        Args:
            path: Path to image file.
            provider: LLM provider name (or None for default).
            callback: Called with AnalysisResult when complete.
        """
        async def _run():
            from .analyzer import Analyzer
            analyzer = Analyzer(self._config)
            try:
                result = await analyzer.analyze_image(
                    path, provider=provider, save_txt=True
                )
                return {
                    "success": result.success,
                    "content": result.content if result.success else None,
                    "error": result.error if not result.success else None,
                    "inference_time": result.inference_time,
                }
            finally:
                await analyzer.close()

        self._submit(_run, callback)

    def health_check(self, callback=None):
        """Submit health check.

        Args:
            callback: Called with dict of {provider: bool} results.
        """
        async def _run():
            from .analyzer import Analyzer
            analyzer = Analyzer(self._config)
            try:
                return await analyzer.health_check()
            finally:
                await analyzer.close()

        self._submit(_run, callback)
