#!/usr/bin/env python3
"""
Unified Analyzer
Integrates LLM clients and report generator for comprehensive analysis
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .config import Config, get_config
from .llm_client import LLMRouter, AnalysisResult
from .report_generator import (
    ReportGenerator,
    ReportAggregator,
    ImageAnalysis,
    KeyboardSession,
)

logger = logging.getLogger(__name__)


class Analyzer:
    """Unified analyzer for screenshots and logs"""

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize analyzer

        Args:
            config: Configuration instance, uses global config if None
        """
        self.config = config or get_config()
        self.llm_router = LLMRouter(self.config.get_llm_config())
        self.report_generator = ReportGenerator(
            output_dir=self.config.get_output_dir(),
            reports_subdir=self.config.get("reports.output_dir", "reports"),
            include_images=self.config.get("reports.include_images", True),
        )
        self.report_aggregator = ReportAggregator(
            self.report_generator,
            self.llm_router
        )

    async def health_check(self) -> Dict[str, bool]:
        """Check health status of all LLM providers"""
        return await self.llm_router.health_check_all()

    def _parse_image_info(self, image_path: Path) -> Dict[str, Any]:
        """Parse action info from image path"""
        filename = image_path.stem
        info = {
            "action": "default",
            "x": 0,
            "y": 0,
            "x1": 0,
            "y1": 0,
            "x2": 0,
            "y2": 0,
        }

        if filename.startswith("click_"):
            info["action"] = "click"
        elif filename.startswith("dblclick_"):
            info["action"] = "dblclick"
        elif filename.startswith("drag_"):
            info["action"] = "drag"

        # Parse coordinates
        x_match = re.search(r'_x(-?\d+)', filename)
        y_match = re.search(r'_y(-?\d+)', filename)
        if x_match:
            info["x"] = info["x1"] = int(x_match.group(1))
        if y_match:
            info["y"] = info["y1"] = int(y_match.group(1))

        # Drag endpoint
        to_match = re.search(r'_to_x(-?\d+)_y(-?\d+)', filename)
        if to_match:
            info["x2"] = int(to_match.group(1))
            info["y2"] = int(to_match.group(2))

        return info

    async def analyze_image(
        self,
        image_path: str,
        provider: Optional[str] = None,
        save_txt: bool = True
    ) -> AnalysisResult:
        """
        Analyze a single image

        Args:
            image_path: Image path
            provider: LLM provider
            save_txt: Save result as txt file

        Returns:
            AnalysisResult: Analysis result
        """
        image_path = Path(image_path)
        if not image_path.exists():
            return AnalysisResult(
                success=False,
                error=f"Image not found: {image_path}"
            )

        # Parse image info
        info = self._parse_image_info(image_path)
        action = info["action"]

        # Get prompt
        prompt = self.config.get_image_prompt(action, **info)
        system_prompt = self.config.get_system_prompt("image")

        # Call LLM
        result = await self.llm_router.analyze_image(
            str(image_path),
            prompt,
            system_prompt,
            provider=provider
        )

        # Save txt file
        if save_txt and result.success:
            metadata = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": action,
                "position": f"({info['x']}, {info['y']})" if action != "drag"
                           else f"({info['x1']}, {info['y1']}) -> ({info['x2']}, {info['y2']})",
            }
            self.report_generator.generate_image_txt(
                image_path,
                result.content,
                metadata
            )

        return result

    async def analyze_keyboard_log(
        self,
        content: str,
        window: str = "Unknown",
        provider: Optional[str] = None
    ) -> AnalysisResult:
        """
        Analyze keyboard log

        Args:
            content: Keyboard input content
            window: Window name
            provider: LLM provider

        Returns:
            AnalysisResult: Analysis result
        """
        prompt = self.config.get_keyboard_prompt(window=window, content=content)
        system_prompt = self.config.get_system_prompt("keyboard")

        return await self.llm_router.analyze_text(
            content,
            prompt,
            system_prompt,
            provider=provider
        )

    async def analyze_images_batch(
        self,
        date_dir: Path,
        limit: Optional[int] = None,
        skip_existing: bool = True,
        provider: Optional[str] = None
    ) -> int:
        """
        Batch analyze images in directory

        Args:
            date_dir: Date directory
            limit: Limit number of images
            skip_existing: Skip images with existing txt files
            provider: LLM provider

        Returns:
            int: Number of successfully analyzed images
        """
        # Get images to analyze
        if skip_existing:
            images = self.report_generator.get_unanalyzed_images(date_dir)
        else:
            images = sorted(date_dir.glob("*.webp"))

        if limit:
            images = images[:limit]

        if not images:
            logger.info("No images to analyze")
            return 0

        logger.info(f"Analyzing {len(images)} images...")

        batch_size = self.config.get("scheduler.batch_size", 10)
        delay = self.config.get("scheduler.delay_between_batches", 2)

        success_count = 0

        for i, image_path in enumerate(images):
            logger.info(f"[{i+1}/{len(images)}] {image_path.name}")

            result = await self.analyze_image(
                str(image_path),
                provider=provider,
                save_txt=True
            )

            if result.success:
                success_count += 1
                logger.info(f"  Done: {result.inference_time:.2f}s")
            else:
                logger.warning(f"  Failed: {result.error}")

            # Delay between batches
            if (i + 1) % batch_size == 0 and i + 1 < len(images):
                await asyncio.sleep(delay)

        logger.info(f"Complete! Success: {success_count}/{len(images)}")
        return success_count

    async def analyze_day(
        self,
        date_str: Optional[str] = None,
        analyze_images: bool = True,
        analyze_logs: bool = True,
        generate_reports: bool = True,
        provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze all data for a specific day

        Args:
            date_str: Date string (YYYY-MM-DD), defaults to today
            analyze_images: Analyze images
            analyze_logs: Analyze logs
            generate_reports: Generate reports
            provider: LLM provider

        Returns:
            Dict: Analysis statistics
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        date_dir = self.config.get_output_dir() / date_str

        if not date_dir.exists():
            logger.error(f"Directory not found: {date_dir}")
            return {"error": f"Directory not found: {date_dir}"}

        results = {
            "date": date_str,
            "images_analyzed": 0,
            "logs_analyzed": 0,
            "reports_generated": [],
        }

        # Analyze images
        if analyze_images:
            results["images_analyzed"] = await self.analyze_images_batch(
                date_dir,
                skip_existing=True,
                provider=provider
            )

        # Analyze logs (if enabled)
        if analyze_logs:
            log_file = date_dir / f"{date_str}.log"
            if log_file.exists():
                sessions = self.report_aggregator.parse_log_file(log_file)
                results["logs_analyzed"] = len(sessions)

        # Generate reports
        if generate_reports:
            reports = await self.report_aggregator.generate_reports_for_date(
                date_str,
                generate_summary=self.config.get("reports.daily_summary", True)
            )
            results["reports_generated"] = list(reports.values())

        return results

    async def analyze_today(self, **kwargs) -> Dict[str, Any]:
        """Analyze today's data"""
        return await self.analyze_day(
            datetime.now().strftime("%Y-%m-%d"),
            **kwargs
        )

    def list_available_dates(self) -> List[str]:
        """List all available date directories"""
        output_dir = self.config.get_output_dir()
        dates = []

        for d in output_dir.iterdir():
            if d.is_dir() and re.match(r'\d{4}-\d{2}-\d{2}', d.name):
                dates.append(d.name)

        return sorted(dates, reverse=True)


async def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="OpenCapture Analyzer - Multi-provider LLM support"
    )
    parser.add_argument(
        "-c", "--config",
        help="Configuration file path"
    )
    parser.add_argument(
        "-d", "--dir",
        default="~/auto-capture",
        help="Data directory (default: ~/auto-capture)"
    )
    parser.add_argument(
        "--date",
        help="Analyze specific date (YYYY-MM-DD), default: today"
    )
    parser.add_argument(
        "--image",
        help="Analyze single image"
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "anthropic", "custom"],
        help="LLM provider"
    )
    parser.add_argument(
        "--no-reports",
        action="store_true",
        help="Skip report generation"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of images to analyze"
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Check LLM service status"
    )
    parser.add_argument(
        "--list-dates",
        action="store_true",
        help="List available dates"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Initialize config
    from .config import init_config
    config = init_config(args.config)

    if args.dir != "~/auto-capture":
        config.set("capture.output_dir", str(Path(args.dir).expanduser()))

    # Create analyzer
    analyzer = Analyzer(config)

    print("=" * 60)
    print("OpenCapture Analyzer")
    print(f"Data directory: {config.get_output_dir()}")
    print(f"Default provider: {config.get_default_provider()}")
    print("=" * 60)

    # Health check
    if args.health_check:
        print("\nChecking LLM services...")
        status = await analyzer.health_check()
        for provider, ok in status.items():
            icon = "OK" if ok else "FAIL"
            print(f"  [{icon}] {provider}")
        return

    # List dates
    if args.list_dates:
        print("\nAvailable dates:")
        for date in analyzer.list_available_dates():
            print(f"  - {date}")
        return

    # Analyze single image
    if args.image:
        print(f"\nAnalyzing image: {args.image}")
        result = await analyzer.analyze_image(
            args.image,
            provider=args.provider,
            save_txt=True
        )
        if result.success:
            print(f"\n{result.content}")
            print(f"\n[Time: {result.inference_time:.2f}s]")
        else:
            print(f"\nError: {result.error}")
        return

    # Analyze specific date
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    print(f"\nAnalyzing date: {date_str}")

    results = await analyzer.analyze_day(
        date_str,
        generate_reports=not args.no_reports,
        provider=args.provider
    )

    print("\n" + "=" * 60)
    print("Analysis Complete")
    print("=" * 60)
    print(f"Images analyzed: {results.get('images_analyzed', 0)}")
    print(f"Logs parsed: {results.get('logs_analyzed', 0)}")

    if results.get("reports_generated"):
        print("\nGenerated reports:")
        for report in results["reports_generated"]:
            print(f"  - {report}")


if __name__ == "__main__":
    asyncio.run(main())
