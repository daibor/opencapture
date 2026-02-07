#!/usr/bin/env python3
"""
Markdown Report Generator
Generates structured Markdown documents from AI analysis results
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ImageAnalysis:
    """Image analysis result"""
    filename: str
    filepath: str
    timestamp: datetime
    action: str  # click, dblclick, drag
    position: tuple  # (x, y) or (x1, y1, x2, y2)
    analysis: str
    window_title: str = ""
    window_app: str = ""
    inference_time: float = 0.0


@dataclass
class KeyboardSession:
    """Keyboard session data"""
    timestamp: datetime
    window_title: str
    window_app: str
    content: str
    analysis: str = ""
    screenshots: List[str] = field(default_factory=list)


@dataclass
class DailyReport:
    """Daily report data"""
    date: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    window_count: int = 0
    screenshot_count: int = 0
    main_apps: List[str] = field(default_factory=list)
    keyboard_sessions: List[KeyboardSession] = field(default_factory=list)
    image_analyses: List[ImageAnalysis] = field(default_factory=list)
    summary: str = ""


class ReportGenerator:
    """Markdown report generator"""

    def __init__(
        self,
        output_dir: Path,
        reports_subdir: str = "reports",
        include_images: bool = True
    ):
        """
        Initialize report generator

        Args:
            output_dir: Data root directory (e.g., ~/auto-capture)
            reports_subdir: Reports subdirectory name
            include_images: Include image references in reports
        """
        self.output_dir = Path(output_dir).expanduser()
        self.reports_dir = self.output_dir / reports_subdir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.include_images = include_images

    def _parse_filename(self, filename: str) -> Dict[str, Any]:
        """
        Parse screenshot filename to extract action info

        Filename format: action_HHmmss_ms_button_x<X>_y<Y>.webp
        """
        info = {
            "action": "unknown",
            "time": None,
            "button": "left",
            "x": None,
            "y": None,
            "x2": None,
            "y2": None,
        }

        stem = Path(filename).stem

        # Parse action type
        if stem.startswith("click_"):
            info["action"] = "click"
        elif stem.startswith("dblclick_"):
            info["action"] = "dblclick"
        elif stem.startswith("drag_"):
            info["action"] = "drag"

        # Parse time (HHmmss_ms)
        time_match = re.search(r'_(\d{6})_(\d{3})_', stem)
        if time_match:
            time_str = time_match.group(1)
            try:
                info["time"] = datetime.strptime(time_str, "%H%M%S").time()
            except ValueError:
                pass

        # Parse coordinates
        x_match = re.search(r'_x(-?\d+)', stem)
        y_match = re.search(r'_y(-?\d+)', stem)
        if x_match:
            info["x"] = int(x_match.group(1))
        if y_match:
            info["y"] = int(y_match.group(1))

        # Drag endpoint
        if info["action"] == "drag":
            to_match = re.search(r'_to_x(-?\d+)_y(-?\d+)', stem)
            if to_match:
                info["x2"] = int(to_match.group(1))
                info["y2"] = int(to_match.group(2))

        # Parse button
        if "_right_" in stem:
            info["button"] = "right"

        return info

    def _action_to_text(self, action: str) -> str:
        """Convert action type to display text"""
        mapping = {
            "click": "Click",
            "dblclick": "Double-click",
            "drag": "Drag",
            "unknown": "Action",
        }
        return mapping.get(action, action)

    def _format_position(self, info: Dict[str, Any]) -> str:
        """Format position information"""
        if info["action"] == "drag" and info.get("x2") is not None:
            return f"({info['x']}, {info['y']}) → ({info['x2']}, {info['y2']})"
        elif info.get("x") is not None:
            return f"({info['x']}, {info['y']})"
        return ""

    def generate_daily_report(
        self,
        date_str: str,
        keyboard_sessions: List[KeyboardSession],
        image_analyses: List[ImageAnalysis],
        summary: str = ""
    ) -> str:
        """
        Generate daily comprehensive report

        Args:
            date_str: Date string (YYYY-MM-DD)
            keyboard_sessions: Keyboard session list
            image_analyses: Image analysis list
            summary: AI-generated daily summary

        Returns:
            str: Report file path
        """
        # Collect statistics
        all_apps = set()
        for session in keyboard_sessions:
            if session.window_app:
                app_name = session.window_app.split("(")[0].strip()
                all_apps.add(app_name)

        start_time = None
        end_time = None
        if keyboard_sessions:
            start_time = min(s.timestamp for s in keyboard_sessions)
            end_time = max(s.timestamp for s in keyboard_sessions)
        elif image_analyses:
            start_time = min(a.timestamp for a in image_analyses)
            end_time = max(a.timestamp for a in image_analyses)

        # Generate Markdown
        lines = [
            f"# {date_str} Activity Report",
            "",
            "> Generated by OpenCapture",
            "",
            "## Overview",
            "",
        ]

        if start_time and end_time:
            lines.append(f"- **Time Range**: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")

        lines.append(f"- **Active Windows**: {len(keyboard_sessions)}")
        lines.append(f"- **Screenshots**: {len(image_analyses)}")

        if all_apps:
            lines.append(f"- **Main Apps**: {', '.join(sorted(all_apps)[:5])}")

        lines.extend(["", "---", ""])

        # Daily summary
        if summary:
            lines.extend([
                "## Summary",
                "",
                summary,
                "",
                "---",
                "",
            ])

        # Timeline
        lines.extend([
            "## Activity Timeline",
            "",
        ])

        # Sort sessions by time
        sorted_sessions = sorted(keyboard_sessions, key=lambda s: s.timestamp)

        for session in sorted_sessions:
            time_str = session.timestamp.strftime("%H:%M")
            app_name = session.window_app.split("(")[0].strip() if session.window_app else "Unknown"

            lines.extend([
                f"### {time_str} | {app_name}",
                "",
            ])

            if session.window_title:
                lines.append(f"**Window**: {session.window_title}")
                lines.append("")

            if session.content:
                lines.extend([
                    "**Input**:",
                    "```",
                    session.content[:500] + ("..." if len(session.content) > 500 else ""),
                    "```",
                    "",
                ])

            if session.analysis:
                lines.extend([
                    "**AI Analysis**:",
                    "",
                    session.analysis,
                    "",
                ])

            # Related screenshots
            if session.screenshots and self.include_images:
                lines.append("**Screenshots**:")
                for screenshot in session.screenshots[:3]:
                    rel_path = f"../{date_str}/{screenshot}"
                    lines.append(f"- [{screenshot}]({rel_path})")
                lines.append("")

            lines.append("---")
            lines.append("")

        # Save report
        report_path = self.reports_dir / f"{date_str}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"Generated daily report: {report_path}")
        return str(report_path)

    def generate_images_report(
        self,
        date_str: str,
        image_analyses: List[ImageAnalysis]
    ) -> str:
        """
        Generate image analysis detail report

        Args:
            date_str: Date string
            image_analyses: Image analysis list

        Returns:
            str: Report file path
        """
        lines = [
            f"# {date_str} Screenshot Analysis",
            "",
            "> Generated by OpenCapture AI",
            "",
            f"Total: {len(image_analyses)} screenshots",
            "",
            "---",
            "",
        ]

        # Sort by time
        sorted_analyses = sorted(image_analyses, key=lambda a: a.timestamp)

        for i, analysis in enumerate(sorted_analyses, 1):
            time_str = analysis.timestamp.strftime("%H:%M:%S")
            action_text = self._action_to_text(analysis.action)
            info = self._parse_filename(analysis.filename)
            position = self._format_position(info)

            lines.extend([
                f"## {i}. {analysis.filename}",
                "",
            ])

            # Image reference
            if self.include_images:
                rel_path = f"../{date_str}/{analysis.filename}"
                lines.extend([
                    f"![Screenshot]({rel_path})",
                    "",
                ])

            # Metadata table
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")
            lines.append(f"| **Time** | {time_str} |")
            lines.append(f"| **Action** | {action_text} |")
            if position:
                lines.append(f"| **Position** | {position} |")
            if analysis.window_title:
                lines.append(f"| **Window** | {analysis.window_title} |")
            if analysis.window_app:
                lines.append(f"| **App** | {analysis.window_app} |")
            if analysis.inference_time > 0:
                lines.append(f"| **Inference Time** | {analysis.inference_time:.2f}s |")

            lines.append("")

            # AI analysis content
            if analysis.analysis:
                lines.extend([
                    "### AI Analysis",
                    "",
                    analysis.analysis,
                    "",
                ])

            lines.extend(["---", ""])

        # Save report
        report_path = self.reports_dir / f"{date_str}_images.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"Generated image report: {report_path}")
        return str(report_path)

    def generate_image_txt(
        self,
        image_path: Path,
        analysis: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Generate txt description file for a single image

        Args:
            image_path: Image path
            analysis: Analysis content
            metadata: Optional metadata

        Returns:
            str: txt file path
        """
        txt_path = image_path.with_suffix(".txt")

        lines = []

        # Add metadata (optional)
        if metadata:
            if metadata.get("timestamp"):
                lines.append(f"Time: {metadata['timestamp']}")
            if metadata.get("action"):
                lines.append(f"Action: {self._action_to_text(metadata['action'])}")
            if metadata.get("position"):
                lines.append(f"Position: {metadata['position']}")
            if metadata.get("window"):
                lines.append(f"Window: {metadata['window']}")
            if lines:
                lines.extend(["", "---", ""])

        lines.append(analysis)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.debug(f"Generated: {txt_path.name}")
        return str(txt_path)

    def load_existing_analyses(self, date_dir: Path) -> Dict[str, str]:
        """
        Load existing analysis results from txt files

        Args:
            date_dir: Date directory

        Returns:
            Dict[str, str]: filename -> analysis content
        """
        analyses = {}
        for txt_file in date_dir.glob("*.txt"):
            image_name = txt_file.stem + ".webp"
            if (date_dir / image_name).exists():
                with open(txt_file, "r", encoding="utf-8") as f:
                    analyses[image_name] = f.read()
        return analyses

    def get_unanalyzed_images(self, date_dir: Path) -> List[Path]:
        """
        Get list of images without analysis

        Args:
            date_dir: Date directory

        Returns:
            List[Path]: Unanalyzed image paths
        """
        unanalyzed = []
        for img_file in date_dir.glob("*.webp"):
            txt_file = img_file.with_suffix(".txt")
            if not txt_file.exists():
                unanalyzed.append(img_file)
        return sorted(unanalyzed)

    def generate_audio_txt(
        self,
        audio_path: Path,
        transcription: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Generate txt transcription file for a single audio recording.

        Follows the same pattern as generate_image_txt:
        mic_*.wav → mic_*.txt (same base name)

        Args:
            audio_path: Audio file path
            transcription: Transcription text
            metadata: Optional metadata (timestamp, app, duration)

        Returns:
            str: txt file path
        """
        txt_path = audio_path.with_suffix(".txt")

        lines = []

        if metadata:
            if metadata.get("timestamp"):
                lines.append(f"Time: {metadata['timestamp']}")
            if metadata.get("app"):
                lines.append(f"App: {metadata['app']}")
            if metadata.get("duration"):
                lines.append(f"Duration: {metadata['duration']}")
            if lines:
                lines.extend(["", "---", ""])

        lines.append(transcription)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.debug(f"Generated: {txt_path.name}")
        return str(txt_path)

    def get_unanalyzed_audios(self, date_dir: Path) -> List[Path]:
        """
        Get list of audio files without transcription.

        Args:
            date_dir: Date directory

        Returns:
            List[Path]: Audio files without corresponding .txt
        """
        unanalyzed = []
        for wav_file in date_dir.glob("mic_*.wav"):
            txt_file = wav_file.with_suffix(".txt")
            if not txt_file.exists():
                unanalyzed.append(wav_file)
        return sorted(unanalyzed)


class ReportAggregator:
    """Report aggregator - generates reports from analysis results"""

    def __init__(self, generator: ReportGenerator, llm_router=None):
        """
        Initialize aggregator

        Args:
            generator: Report generator
            llm_router: LLM router (for generating summaries)
        """
        self.generator = generator
        self.llm_router = llm_router

    def parse_log_file(self, log_path: Path) -> List[KeyboardSession]:
        """Parse log file into keyboard sessions"""
        if not log_path.exists():
            return []

        sessions = []
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by window blocks (triple newlines)
        blocks = content.split("\n\n\n")

        for block in blocks:
            if not block.strip():
                continue

            lines = block.strip().split("\n")
            if not lines:
                continue

            session = None

            for line in lines:
                # Parse window header line
                header_match = re.match(
                    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+?) \| (.+?) \((.+?)\)',
                    line
                )
                if header_match:
                    timestamp_str, app_name, title, bundle_id = header_match.groups()
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    session = KeyboardSession(
                        timestamp=timestamp,
                        window_title=title,
                        window_app=f"{app_name} ({bundle_id})",
                        content="",
                        screenshots=[],
                    )
                    continue

                # Simple format
                simple_match = re.match(
                    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+?) \((.+?)\)',
                    line
                )
                if simple_match and not session:
                    timestamp_str, app_name, bundle_id = simple_match.groups()
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    session = KeyboardSession(
                        timestamp=timestamp,
                        window_title=app_name,
                        window_app=bundle_id,
                        content="",
                        screenshots=[],
                    )
                    continue

                # Screenshot record
                screenshot_match = re.search(r'📷 \w+ \([^)]+\) (.+\.webp)', line)
                if screenshot_match and session:
                    session.screenshots.append(screenshot_match.group(1))
                    continue

                # Timestamp line content
                time_content = re.match(r'\[(\d{2}:\d{2}:\d{2})\] (.+)', line)
                if time_content and session:
                    content = time_content.group(2)
                    if not content.startswith('📷'):
                        session.content += content + "\n"
                    continue

                # Other content
                if session and line.strip():
                    session.content += line + "\n"

            if session:
                session.content = session.content.strip()
                sessions.append(session)

        return sessions

    def load_image_analyses(self, date_dir: Path) -> List[ImageAnalysis]:
        """Load image analyses from txt files"""
        analyses = []

        for img_file in sorted(date_dir.glob("*.webp")):
            txt_file = img_file.with_suffix(".txt")
            if not txt_file.exists():
                continue

            with open(txt_file, "r", encoding="utf-8") as f:
                analysis_text = f.read()

            # Parse filename
            info = self.generator._parse_filename(img_file.name)

            # Build timestamp
            date_str = date_dir.name
            if info["time"]:
                timestamp = datetime.strptime(
                    f"{date_str} {info['time'].strftime('%H:%M:%S')}",
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                timestamp = datetime.strptime(date_str, "%Y-%m-%d")

            # Determine position
            if info["action"] == "drag":
                position = (info["x"], info["y"], info.get("x2"), info.get("y2"))
            else:
                position = (info["x"], info["y"])

            analyses.append(ImageAnalysis(
                filename=img_file.name,
                filepath=str(img_file),
                timestamp=timestamp,
                action=info["action"],
                position=position,
                analysis=analysis_text,
            ))

        return analyses

    async def generate_daily_summary(
        self,
        sessions: List[KeyboardSession],
        analyses: List[ImageAnalysis]
    ) -> str:
        """Generate daily summary using LLM"""
        if not self.llm_router:
            return ""

        # Build activity summary
        activities = []
        for session in sessions[:10]:  # Limit count
            activities.append(
                f"- [{session.timestamp.strftime('%H:%M')}] {session.window_app}: "
                f"{session.content[:100]}..."
            )

        activities_text = "\n".join(activities) if activities else "No keyboard activity recorded"

        prompt = f"""Based on the following daily activity records, generate a brief report:

## Activity Records
{activities_text}

## Screenshot Count
Total {len(analyses)} screenshots

Please generate a brief report (100-200 words) including:
1. Main work today
2. Most used applications
3. Notable activities"""

        result = await self.llm_router.analyze_text(
            text="",
            prompt=prompt,
            temperature=0.5
        )

        return result.content if result.success else ""

    async def generate_reports_for_date(
        self,
        date_str: str,
        generate_summary: bool = True
    ) -> Dict[str, str]:
        """
        Generate all reports for specified date

        Args:
            date_str: Date string (YYYY-MM-DD)
            generate_summary: Generate AI summary

        Returns:
            Dict[str, str]: report type -> file path
        """
        date_dir = self.generator.output_dir / date_str
        if not date_dir.exists():
            logger.error(f"Directory not found: {date_dir}")
            return {}

        # Parse log
        log_file = date_dir / f"{date_str}.log"
        sessions = self.parse_log_file(log_file)

        # Load image analyses
        analyses = self.load_image_analyses(date_dir)

        # Generate summary
        summary = ""
        if generate_summary and self.llm_router:
            summary = await self.generate_daily_summary(sessions, analyses)

        reports = {}

        # Generate daily report
        if sessions or analyses:
            reports["daily"] = self.generator.generate_daily_report(
                date_str, sessions, analyses, summary
            )

        # Generate image analysis report
        if analyses:
            reports["images"] = self.generator.generate_images_report(
                date_str, analyses
            )

        return reports


# CLI interface
async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate Markdown analysis reports")
    parser.add_argument(
        "-d", "--dir",
        default="~/auto-capture",
        help="Data directory"
    )
    parser.add_argument(
        "--date",
        help="Date (YYYY-MM-DD), default: today"
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip AI summary generation"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    output_dir = Path(args.dir).expanduser()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")

    generator = ReportGenerator(output_dir)
    aggregator = ReportAggregator(generator)

    reports = await aggregator.generate_reports_for_date(
        date_str,
        generate_summary=not args.no_summary
    )

    if reports:
        print("\nGenerated reports:")
        for report_type, path in reports.items():
            print(f"  - {report_type}: {path}")
    else:
        print("No reports generated")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
