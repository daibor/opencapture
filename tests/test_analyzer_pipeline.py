"""Tests for the full analyzer pipeline (analyzer.py).

All LLM calls are mocked — no real Ollama needed.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opencapture.config import Config
from opencapture.analyzer import Analyzer
from opencapture.llm_client import AnalysisResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def config(tmp_path, monkeypatch):
    """Config with output_dir pointing at tmp_path."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    cfg = Config()
    cfg.set("capture.output_dir", str(tmp_path))
    return cfg


@pytest.fixture()
def analyzer(config):
    return Analyzer(config=config)


def _ok_result(content="mock analysis"):
    return AnalysisResult(success=True, content=content, inference_time=0.1)


def _err_result(error="mock error"):
    return AnalysisResult(success=False, error=error)


# ---------------------------------------------------------------------------
# analyze_image
# ---------------------------------------------------------------------------

class TestAnalyzeImage:
    @pytest.mark.asyncio
    async def test_success(self, analyzer, tmp_path):
        img = tmp_path / "click_120000_000_left_x100_y200.webp"
        img.write_bytes(b"\x00")  # dummy

        with patch.object(
            analyzer.config, "get_image_prompt", return_value="test prompt",
        ), patch.object(
            analyzer.config, "get_system_prompt", return_value="system",
        ), patch.object(
            analyzer.llm_router, "analyze_image", new_callable=AsyncMock,
            return_value=_ok_result("User clicked a button"),
        ):
            result = await analyzer.analyze_image(str(img), save_txt=True)

        assert result.success
        assert result.content == "User clicked a button"
        # .txt companion should exist
        assert img.with_suffix(".txt").exists()

    @pytest.mark.asyncio
    async def test_not_found(self, analyzer, tmp_path):
        result = await analyzer.analyze_image(
            str(tmp_path / "nonexistent.webp")
        )
        assert not result.success
        assert "not found" in result.error


# ---------------------------------------------------------------------------
# analyze_keyboard_log
# ---------------------------------------------------------------------------

class TestAnalyzeKeyboardLog:
    @pytest.mark.asyncio
    async def test_prompt_contains_window_and_content(self, analyzer):
        with patch.object(
            analyzer.llm_router, "analyze_text", new_callable=AsyncMock,
            return_value=_ok_result("Editing code"),
        ) as mock_text:
            result = await analyzer.analyze_keyboard_log(
                "print('hello')", window="VS Code"
            )

        assert result.success
        # Verify the prompt was built with window and content
        call_kwargs = mock_text.call_args
        assert "VS Code" in str(call_kwargs)


# ---------------------------------------------------------------------------
# analyze_images_batch — skip existing
# ---------------------------------------------------------------------------

class TestAnalyzeImagesBatch:
    @pytest.mark.asyncio
    async def test_skip_existing(self, analyzer, tmp_path):
        # Create image + existing txt → should be skipped
        img = tmp_path / "click_120000_000_left_x100_y200.webp"
        img.write_bytes(b"\x00")
        img.with_suffix(".txt").write_text("already analyzed")

        with patch.object(
            analyzer.llm_router, "analyze_image", new_callable=AsyncMock,
        ) as mock_img:
            success, failed = await analyzer.analyze_images_batch(
                tmp_path, skip_existing=True
            )

        assert success == 0
        assert failed == 0
        mock_img.assert_not_called()

    @pytest.mark.asyncio
    async def test_progress_callback(self, analyzer, tmp_path):
        img1 = tmp_path / "click_120000_000_left_x100_y200.webp"
        img2 = tmp_path / "click_120001_000_left_x200_y300.webp"
        img1.write_bytes(b"\x00")
        img2.write_bytes(b"\x00")

        progress_calls = []

        def on_progress(stage, current, total, detail):
            progress_calls.append((stage, current, total, detail))

        with patch.object(
            analyzer, "analyze_image", new_callable=AsyncMock,
            return_value=_ok_result(),
        ):
            await analyzer.analyze_images_batch(
                tmp_path, skip_existing=True, on_progress=on_progress
            )

        assert len(progress_calls) == 2
        assert progress_calls[0][0] == "images"
        assert progress_calls[0][1] == 1
        assert progress_calls[0][2] == 2
        assert progress_calls[1][1] == 2

    @pytest.mark.asyncio
    async def test_cancel_event(self, analyzer, tmp_path):
        # Create 3 images
        for i in range(3):
            (tmp_path / f"click_12000{i}_000_left_x{i}_y0.webp").write_bytes(b"\x00")

        cancel = asyncio.Event()
        call_count = 0

        async def fake_analyze(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                cancel.set()  # cancel after 2nd image
            return _ok_result()

        with patch.object(
            analyzer, "analyze_image", side_effect=fake_analyze,
        ):
            success, failed = await analyzer.analyze_images_batch(
                tmp_path, skip_existing=True, cancel_event=cancel
            )

        # Should have processed 2 (cancel checked before 3rd)
        assert success == 2


# ---------------------------------------------------------------------------
# analyze_day — full pipeline
# ---------------------------------------------------------------------------

class TestAnalyzeDay:
    def _setup_date_dir(self, tmp_path, date_str="2026-01-15"):
        """Create a date dir with images and a log file."""
        date_dir = tmp_path / date_str
        date_dir.mkdir()

        # One image
        (date_dir / "click_120000_000_left_x100_y200.webp").write_bytes(b"\x00")

        # Log file with one session
        log_content = (
            f"[{date_str} 10:00:00] VS Code | main.py (com.microsoft.VSCode)\n"
            f"[10:00:01] ⌨️ print('hello')\n"
        )
        (date_dir / f"{date_str}.log").write_text(log_content)

        return date_dir

    @pytest.mark.asyncio
    async def test_full_pipeline(self, analyzer, tmp_path):
        date_str = "2026-01-15"
        self._setup_date_dir(tmp_path, date_str)

        with patch.object(
            analyzer, "preflight_check", new_callable=AsyncMock, return_value=True,
        ), patch.object(
            analyzer, "analyze_image", new_callable=AsyncMock,
            return_value=_ok_result("image analysis"),
        ), patch.object(
            analyzer.llm_router, "analyze_text", new_callable=AsyncMock,
            return_value=_ok_result("keyboard analysis"),
        ):
            results = await analyzer.analyze_day(date_str)

        assert results["images_analyzed"] == 1
        assert results["logs_analyzed"] == 1

    @pytest.mark.asyncio
    async def test_keyboard_sessions_analyzed(self, analyzer, tmp_path):
        """Verify session.analysis is filled by LLM."""
        date_str = "2026-01-15"
        self._setup_date_dir(tmp_path, date_str)

        with patch.object(
            analyzer, "preflight_check", new_callable=AsyncMock, return_value=True,
        ), patch.object(
            analyzer, "analyze_image", new_callable=AsyncMock,
            return_value=_ok_result(),
        ), patch.object(
            analyzer.llm_router, "analyze_text", new_callable=AsyncMock,
            return_value=_ok_result("User was editing Python code"),
        ), patch.object(
            analyzer.report_aggregator, "generate_reports_for_date",
            new_callable=AsyncMock, return_value={},
        ):
            results = await analyzer.analyze_day(date_str)

        assert results["logs_analyzed"] == 1

    @pytest.mark.asyncio
    async def test_no_data_dir(self, analyzer):
        results = await analyzer.analyze_day("9999-01-01")
        assert "error" in results

    @pytest.mark.asyncio
    async def test_preflight_fail(self, analyzer, tmp_path):
        date_str = "2026-01-15"
        (tmp_path / date_str).mkdir()

        with patch.object(
            analyzer, "preflight_check", new_callable=AsyncMock, return_value=False,
        ):
            results = await analyzer.analyze_day(date_str)

        assert "error" in results
        assert "not ready" in results["error"]

    @pytest.mark.asyncio
    async def test_progress_stages(self, analyzer, tmp_path):
        date_str = "2026-01-15"
        self._setup_date_dir(tmp_path, date_str)

        stages = []

        def on_progress(stage, current, total, detail):
            stages.append(stage)

        with patch.object(
            analyzer, "preflight_check", new_callable=AsyncMock, return_value=True,
        ), patch.object(
            analyzer, "analyze_image", new_callable=AsyncMock,
            return_value=_ok_result(),
        ), patch.object(
            analyzer.llm_router, "analyze_text", new_callable=AsyncMock,
            return_value=_ok_result(),
        ):
            await analyzer.analyze_day(date_str, on_progress=on_progress)

        assert "preflight" in stages
        assert "images" in stages
        assert "logs" in stages
        assert "reports" in stages
        assert "done" in stages
