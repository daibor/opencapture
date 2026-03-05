"""Tests for AnalysisEngine re-entry guard, cancel, and progress forwarding."""

import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opencapture.config import Config
from opencapture.engine import AnalysisEngine


@pytest.fixture()
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    cfg = Config()
    cfg.set("capture.output_dir", str(tmp_path))
    return cfg


def _mock_analyzer(result=None, delay=0, preflight_ok=True):
    """Return a mock Analyzer class whose analyze_day returns *result*."""
    if result is None:
        result = {"images_analyzed": 1, "logs_analyzed": 0}

    mock_instance = MagicMock()

    async def fake_quick_preflight(*args, **kwargs):
        return {"ok": preflight_ok}

    async def fake_analyze_day(*args, **kwargs):
        if delay:
            import asyncio
            await asyncio.sleep(delay)
        return result

    async def fake_close():
        pass

    mock_instance.quick_preflight = fake_quick_preflight
    mock_instance.analyze_day = fake_analyze_day
    mock_instance.close = fake_close
    return mock_instance


# ---------------------------------------------------------------------------
# Re-entry guard
# ---------------------------------------------------------------------------

class TestReentryGuard:
    def test_prevents_reentry(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        first_done = threading.Event()
        second_called = threading.Event()
        results = []

        def cb(r):
            results.append(r)
            first_done.set()

        with patch("opencapture.analyzer.Analyzer") as MockAnalyzer:
            MockAnalyzer.return_value = _mock_analyzer(delay=0.3)

            engine.analyze_today(callback=cb)
            # Second call while first is running → should be ignored
            engine.analyze_today(callback=lambda r: second_called.set())

            first_done.wait(timeout=5)

        # Only first callback should fire
        assert len(results) == 1
        assert not second_called.is_set()
        engine.stop()

    def test_analyzing_flag_reset_on_complete(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        done = threading.Event()

        with patch("opencapture.analyzer.Analyzer") as MockAnalyzer:
            MockAnalyzer.return_value = _mock_analyzer()
            engine.analyze_today(callback=lambda r: done.set())
            done.wait(timeout=5)

        assert engine.is_analyzing is False
        engine.stop()

    def test_analyzing_flag_reset_on_error(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        done = threading.Event()

        mock_instance = MagicMock()

        async def explode(*a, **kw):
            raise RuntimeError("boom")

        async def fake_close():
            pass

        mock_instance.analyze_day = explode
        mock_instance.close = fake_close

        with patch("opencapture.analyzer.Analyzer") as MockAnalyzer:
            MockAnalyzer.return_value = mock_instance
            engine.analyze_today(callback=lambda r: done.set())
            done.wait(timeout=5)

        assert engine.is_analyzing is False
        engine.stop()


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

class TestCancelAnalysis:
    def test_cancel_sets_event(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        with patch("opencapture.analyzer.Analyzer") as MockAnalyzer:
            MockAnalyzer.return_value = _mock_analyzer(delay=1)
            engine.analyze_today()
            # Give a moment for _analyzing to be set
            time.sleep(0.1)

        assert engine.is_analyzing is True
        engine.cancel_analysis()
        assert engine._cancel_event.is_set()
        engine.stop()


# ---------------------------------------------------------------------------
# Progress forwarding
# ---------------------------------------------------------------------------

class TestProgressForwarding:
    def test_progress_callback_forwarded(self, config):
        engine = AnalysisEngine(config)
        engine.start()

        done = threading.Event()
        progress_calls = []

        mock_instance = MagicMock()

        async def fake_quick_preflight(*args, **kwargs):
            return {"ok": True}

        async def fake_analyze_day(*args, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress("images", 1, 5, "test.webp")
                on_progress("done", 0, 0, "done")
            return {"images_analyzed": 5}

        async def fake_close():
            pass

        mock_instance.quick_preflight = fake_quick_preflight
        mock_instance.analyze_day = fake_analyze_day
        mock_instance.close = fake_close

        def on_progress(stage, current, total, detail):
            progress_calls.append((stage, current, total, detail))

        with patch("opencapture.analyzer.Analyzer") as MockAnalyzer:
            MockAnalyzer.return_value = mock_instance
            engine.analyze_today(
                callback=lambda r: done.set(),
                on_progress=on_progress,
            )
            done.wait(timeout=5)

        assert len(progress_calls) == 3
        assert progress_calls[0] == ("preflight", 0, 0, "Checking LLM provider...")
        assert progress_calls[1] == ("images", 1, 5, "test.webp")
        assert progress_calls[2] == ("done", 0, 0, "done")
        engine.stop()
