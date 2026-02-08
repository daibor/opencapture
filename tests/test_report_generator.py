"""Tests for opencapture/report_generator.py"""

import pytest
from pathlib import Path

from opencapture.report_generator import (
    ReportGenerator,
    ReportAggregator,
    KeyboardSession,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def gen(tmp_path):
    """Return a ReportGenerator rooted at tmp_path."""
    return ReportGenerator(output_dir=tmp_path)


# ---------------------------------------------------------------------------
# _parse_filename
# ---------------------------------------------------------------------------

class TestParseFilename:
    def test_click(self, gen):
        info = gen._parse_filename("click_143022_123_left_x500_y300.webp")
        assert info["action"] == "click"
        assert info["x"] == 500
        assert info["y"] == 300

    def test_dblclick(self, gen):
        info = gen._parse_filename("dblclick_090000_000_left_x10_y20.webp")
        assert info["action"] == "dblclick"
        assert info["x"] == 10
        assert info["y"] == 20

    def test_drag_with_endpoint(self, gen):
        info = gen._parse_filename(
            "drag_120000_000_left_x100_y200_to_x300_y400.webp"
        )
        assert info["action"] == "drag"
        assert info["x"] == 100
        assert info["y"] == 200
        assert info["x2"] == 300
        assert info["y2"] == 400

    def test_negative_coords(self, gen):
        info = gen._parse_filename("click_120000_000_left_x-50_y-100.webp")
        assert info["x"] == -50
        assert info["y"] == -100

    def test_unknown_format(self, gen):
        info = gen._parse_filename("random_file.webp")
        assert info["action"] == "unknown"
        assert info["x"] is None
        assert info["y"] is None


# ---------------------------------------------------------------------------
# _action_to_text
# ---------------------------------------------------------------------------

class TestActionToText:
    @pytest.mark.parametrize(
        "action,expected",
        [
            ("click", "Click"),
            ("dblclick", "Double-click"),
            ("drag", "Drag"),
            ("unknown", "Action"),
        ],
    )
    def test_known_actions(self, gen, action, expected):
        assert gen._action_to_text(action) == expected

    def test_passthrough_unknown(self, gen):
        assert gen._action_to_text("swipe") == "swipe"


# ---------------------------------------------------------------------------
# _format_position
# ---------------------------------------------------------------------------

class TestFormatPosition:
    def test_click_position(self, gen):
        info = {"action": "click", "x": 10, "y": 20, "x2": None, "y2": None}
        assert gen._format_position(info) == "(10, 20)"

    def test_drag_position(self, gen):
        info = {"action": "drag", "x": 10, "y": 20, "x2": 30, "y2": 40}
        result = gen._format_position(info)
        assert "10" in result and "40" in result
        assert "\u2192" in result  # arrow

    def test_no_coords(self, gen):
        info = {"action": "unknown", "x": None, "y": None, "x2": None, "y2": None}
        assert gen._format_position(info) == ""


# ---------------------------------------------------------------------------
# ReportAggregator.parse_log_file
# ---------------------------------------------------------------------------

class TestParseLogFile:
    def test_parses_blocks(self, tmp_path, gen):
        log = tmp_path / "2026-01-01.log"
        log.write_text(
            "[2026-01-01 09:00:00] Terminal | bash (/bin/bash)\n"
            "[09:00:01] ls -la\n"
            "[09:00:02] cd /tmp\n"
            "\n\n\n"
            "[2026-01-01 10:00:00] Safari | Google (/Applications/Safari.app)\n"
            "[10:00:01] search query\n"
        )
        agg = ReportAggregator(gen)
        sessions = agg.parse_log_file(log)
        assert len(sessions) == 2
        assert sessions[0].window_app == "Terminal (/bin/bash)"
        assert "ls -la" in sessions[0].content
        assert sessions[1].window_app == "Safari (/Applications/Safari.app)"

    def test_empty_log(self, tmp_path, gen):
        log = tmp_path / "empty.log"
        log.write_text("")
        agg = ReportAggregator(gen)
        assert agg.parse_log_file(log) == []

    def test_nonexistent_log(self, tmp_path, gen):
        agg = ReportAggregator(gen)
        assert agg.parse_log_file(tmp_path / "nope.log") == []


# ---------------------------------------------------------------------------
# get_unanalyzed_images
# ---------------------------------------------------------------------------

class TestGetUnanalyzedImages:
    def test_filters_analyzed(self, tmp_path, gen):
        (tmp_path / "click_120000_000_left_x10_y20.webp").touch()
        (tmp_path / "click_120000_000_left_x10_y20.txt").touch()  # analyzed
        (tmp_path / "click_130000_000_left_x30_y40.webp").touch()  # not analyzed

        result = gen.get_unanalyzed_images(tmp_path)
        assert len(result) == 1
        assert result[0].name == "click_130000_000_left_x30_y40.webp"

    def test_all_analyzed(self, tmp_path, gen):
        (tmp_path / "click_120000_000_left_x10_y20.webp").touch()
        (tmp_path / "click_120000_000_left_x10_y20.txt").touch()
        assert gen.get_unanalyzed_images(tmp_path) == []

    def test_none_present(self, tmp_path, gen):
        assert gen.get_unanalyzed_images(tmp_path) == []
