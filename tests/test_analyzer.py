"""Tests for opencapture/analyzer.py"""

import re
import pytest
from pathlib import Path

from opencapture.config import Config
from opencapture.analyzer import Analyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def analyzer(tmp_path, monkeypatch):
    """Return an Analyzer whose output_dir points to tmp_path."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    cfg = Config()
    cfg.set("capture.output_dir", str(tmp_path))
    return Analyzer(config=cfg)


# ---------------------------------------------------------------------------
# _parse_image_info
# ---------------------------------------------------------------------------

class TestParseImageInfo:
    def test_click(self, analyzer):
        info = analyzer._parse_image_info(Path("click_143022_123_left_x500_y300.webp"))
        assert info["action"] == "click"
        assert info["x"] == 500
        assert info["y"] == 300

    def test_dblclick(self, analyzer):
        info = analyzer._parse_image_info(Path("dblclick_090000_000_left_x10_y20.webp"))
        assert info["action"] == "dblclick"

    def test_drag(self, analyzer):
        info = analyzer._parse_image_info(
            Path("drag_120000_000_left_x100_y200_to_x300_y400.webp")
        )
        assert info["action"] == "drag"
        assert info["x2"] == 300
        assert info["y2"] == 400

    def test_unknown(self, analyzer):
        info = analyzer._parse_image_info(Path("random.webp"))
        assert info["action"] == "default"


# ---------------------------------------------------------------------------
# list_available_dates
# ---------------------------------------------------------------------------

class TestListAvailableDates:
    def test_filters_and_sorts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        cfg = Config()
        cfg.set("capture.output_dir", str(tmp_path))

        # Create date dirs and non-date dirs
        (tmp_path / "2026-01-15").mkdir()
        (tmp_path / "2026-02-01").mkdir()
        (tmp_path / "2025-12-31").mkdir()
        (tmp_path / "reports").mkdir()
        (tmp_path / "not-a-date").mkdir()

        a = Analyzer(config=cfg)
        dates = a.list_available_dates()

        assert dates == ["2026-02-01", "2026-01-15", "2025-12-31"]
        assert "reports" not in dates
        assert "not-a-date" not in dates
