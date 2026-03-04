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
from typing import Callable, Dict, Any, Optional, List

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
        self.llm_router = LLMRouter(
            self.config.get_llm_config(),
            allow_online=self.config.is_online_allowed(),
            asr_config=self.config.get("asr"),
        )
        self.report_generator = ReportGenerator(
            output_dir=self.config.get_output_dir(),
            reports_subdir=self.config.get("reports.output_dir", "reports"),
            include_images=self.config.get("reports.include_images", True),
        )
        self.report_aggregator = ReportAggregator(
            self.report_generator,
            self.llm_router
        )

    async def close(self):
        """Close all underlying LLM client sessions"""
        await self.llm_router.close()

    async def health_check(self) -> Dict[str, bool]:
        """Check health status of all LLM providers"""
        return await self.llm_router.health_check_all()

    async def preflight_check(self, provider: Optional[str] = None) -> bool:
        """
        Pre-flight check before analysis. Returns True if ready.
        Prints actionable guidance on failure.
        """
        provider = provider or self.config.get_default_provider()

        # Block remote providers when online mode is disabled
        if self.config.is_remote_provider(provider) and not self.config.is_online_allowed():
            print(
                f"\n\033[1;31m[Error] Remote provider '{provider}' is blocked"
                f" — online mode is disabled.\033[0m\n"
                f"\n"
                f"Your data includes screenshots and keyboard logs.\n"
                f"Sending to remote servers requires explicit opt-in.\n"
                f"\n"
                f"To enable:\n"
                f"  1. Set in config:  privacy.allow_online: true\n"
                f"  2. Or env var:     export OPENCAPTURE_ALLOW_ONLINE=true\n"
                f"\n"
                f"To use local analysis instead:\n"
                f"  ollama pull qwen2-vl:7b\n"
                f"  opencapture --analyze today\n"
            )
            return False

        client = self.llm_router.get_client(provider)

        if not client:
            enabled = self.llm_router.list_providers()
            print(f"\n[Error] Provider '{provider}' is not configured.")
            if enabled:
                print(f"Available providers: {', '.join(enabled)}")
                print(f"Use: --provider {enabled[0]}")
            else:
                print("No LLM providers are enabled.")
                print("\nTo use Ollama (local):")
                print("  1. Install: https://ollama.ai")
                print("  2. Start:   ollama serve")
                print("  3. Pull:    ollama pull qwen2-vl:7b")
                print("\nOr use a remote API:")
                print("  export OPENAI_API_KEY=sk-xxx")
                print("  opencapture --provider openai --analyze today")
            return False

        ok = await client.health_check()
        if not ok:
            print(f"\n[Error] Provider '{provider}' is not ready.")
            if provider == "ollama":
                print("\nTroubleshooting:")
                print("  1. Is Ollama installed?")
                print("     brew install ollama  (macOS)")
                print("     curl -fsSL https://ollama.ai/install.sh | sh  (Linux)")
                print(f"  2. Is Ollama running?")
                print(f"     ollama serve")
                print(f"  3. Is the model downloaded?")
                print(f"     ollama pull {client.model}")
                print(f"     ollama list  (check available models)")
            elif provider in ("openai", "anthropic"):
                env_var = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
                print(f"\n  Ensure {env_var} is set correctly:")
                print(f"  export {env_var}=your-api-key")
            return False

        return True

    def confirm_online_usage(self, provider: Optional[str] = None) -> bool:
        """
        Show colored privacy warning and require user confirmation
        before using a remote LLM provider. Returns True if confirmed.
        """
        provider = provider or self.config.get_default_provider()
        if not self.config.is_remote_provider(provider):
            return True

        provider_names = {
            "openai": "OpenAI API",
            "anthropic": "Anthropic Claude API",
            "custom": "Custom Remote API",
        }
        display_name = provider_names.get(provider, provider)

        YELLOW = "\033[1;33m"
        RED = "\033[1;31m"
        BOLD = "\033[1m"
        NC = "\033[0m"

        print(
            f"\n{YELLOW}"
            f"╔══════════════════════════════════════════════════════════╗\n"
            f"║  ⚠  Privacy Warning — Remote LLM Provider              ║\n"
            f"╚══════════════════════════════════════════════════════════╝"
            f"{NC}\n"
        )
        print(f"  You are about to send data to: {BOLD}{display_name}{NC}")
        print(f"  Data includes:")
        print(f"    {RED}• Screenshots (screen content, visible passwords, personal info){NC}")
        print(f"    {RED}• Keyboard input logs{NC}")
        print()

        try:
            answer = input(f"  Type {BOLD}'yes'{NC} to confirm: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Aborted.")
            return False

        if answer != "yes":
            print("  Aborted. Use local Ollama instead:")
            print("    opencapture --analyze today")
            return False

        print()
        return True

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
        action = info.pop("action")

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
        provider: Optional[str] = None,
        on_progress: Optional[Callable] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> int:
        """
        Batch analyze images in directory

        Args:
            date_dir: Date directory
            limit: Limit number of images
            skip_existing: Skip images with existing txt files
            provider: LLM provider
            on_progress: Callback(stage, current, total, detail)
            cancel_event: asyncio.Event to signal cancellation

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
            if cancel_event and cancel_event.is_set():
                logger.info("Analysis cancelled")
                break

            logger.info(f"[{i+1}/{len(images)}] {image_path.name}")
            if on_progress:
                on_progress("images", i + 1, len(images), image_path.name)

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

    async def analyze_audio(
        self,
        audio_path: str,
        save_txt: bool = True,
    ) -> AnalysisResult:
        """
        Transcribe a single audio file

        Args:
            audio_path: Audio file path
            save_txt: Save result as txt file

        Returns:
            AnalysisResult: Transcription result
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            return AnalysisResult(
                success=False,
                error=f"Audio file not found: {audio_path}"
            )

        result = await self.llm_router.transcribe_audio(str(audio_path))

        if save_txt and result.success:
            # Parse metadata from filename: mic_HHmmss_ms_app_durN.wav
            filename = audio_path.stem
            metadata = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

            # Extract app name
            parts = filename.split("_")
            if len(parts) >= 4:
                # mic_HHmmss_ms_app[_durN]
                app_parts = parts[3:]
                dur_idx = None
                for i, p in enumerate(app_parts):
                    if p.startswith("dur"):
                        dur_idx = i
                        break
                if dur_idx is not None:
                    metadata["app"] = "_".join(app_parts[:dur_idx])
                    metadata["duration"] = app_parts[dur_idx].replace("dur", "") + "s"
                else:
                    metadata["app"] = "_".join(app_parts)

            self.report_generator.generate_audio_txt(
                audio_path, result.content, metadata
            )

        return result

    async def analyze_audios_batch(
        self,
        date_dir: Path,
        limit: Optional[int] = None,
        skip_existing: bool = True,
        on_progress: Optional[Callable] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> int:
        """
        Batch transcribe audio files in directory

        Args:
            date_dir: Date directory
            limit: Limit number of files
            skip_existing: Skip files with existing txt
            on_progress: Callback(stage, current, total, detail)
            cancel_event: asyncio.Event to signal cancellation

        Returns:
            int: Number of successfully transcribed files
        """
        if not self.llm_router.asr_client:
            return 0

        audios = self.report_generator.get_unanalyzed_audios(date_dir)
        if not skip_existing:
            audios = sorted(date_dir.glob("mic_*.wav"))

        if limit:
            audios = audios[:limit]

        if not audios:
            logger.info("No audio files to transcribe")
            return 0

        logger.info(f"Transcribing {len(audios)} audio files...")

        success_count = 0
        for i, audio_path in enumerate(audios):
            if cancel_event and cancel_event.is_set():
                logger.info("Transcription cancelled")
                break

            logger.info(f"[{i+1}/{len(audios)}] {audio_path.name}")
            if on_progress:
                on_progress("audios", i + 1, len(audios), audio_path.name)

            result = await self.analyze_audio(str(audio_path), save_txt=True)

            if result.success:
                success_count += 1
                logger.info(f"  Done: {result.inference_time:.2f}s")
            else:
                logger.warning(f"  Failed: {result.error}")

        logger.info(f"Transcription complete! Success: {success_count}/{len(audios)}")
        return success_count

    async def analyze_day(
        self,
        date_str: Optional[str] = None,
        analyze_images: bool = True,
        analyze_logs: bool = True,
        generate_reports: bool = True,
        provider: Optional[str] = None,
        on_progress: Optional[Callable] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> Dict[str, Any]:
        """
        Analyze all data for a specific day

        Args:
            date_str: Date string (YYYY-MM-DD), defaults to today
            analyze_images: Analyze images
            analyze_logs: Analyze logs
            generate_reports: Generate reports
            provider: LLM provider
            on_progress: Callback(stage, current, total, detail)
            cancel_event: asyncio.Event to signal cancellation

        Returns:
            Dict: Analysis statistics
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        date_dir = self.config.get_output_dir() / date_str

        if not date_dir.exists():
            logger.error(f"Directory not found: {date_dir}")
            return {"error": f"Directory not found: {date_dir}"}

        # Pre-flight check
        if on_progress:
            on_progress("preflight", 0, 0, "Checking LLM provider...")
        if analyze_images or analyze_logs:
            if not await self.preflight_check(provider):
                return {"error": "LLM provider not ready. See above for details."}

        results = {
            "date": date_str,
            "images_analyzed": 0,
            "audios_transcribed": 0,
            "logs_analyzed": 0,
            "reports_generated": [],
        }

        # Analyze images
        if analyze_images:
            if cancel_event and cancel_event.is_set():
                return results
            results["images_analyzed"] = await self.analyze_images_batch(
                date_dir,
                skip_existing=True,
                provider=provider,
                on_progress=on_progress,
                cancel_event=cancel_event,
            )

        # Transcribe audio files
        if self.llm_router.asr_client:
            if cancel_event and cancel_event.is_set():
                return results
            results["audios_transcribed"] = await self.analyze_audios_batch(
                date_dir,
                skip_existing=True,
                on_progress=on_progress,
                cancel_event=cancel_event,
            )

        # Analyze logs — call LLM for each keyboard session
        if analyze_logs:
            log_file = date_dir / f"{date_str}.log"
            if log_file.exists():
                sessions = self.report_aggregator.parse_log_file(log_file)
                analyzed_count = 0
                for i, session in enumerate(sessions):
                    if cancel_event and cancel_event.is_set():
                        logger.info("Log analysis cancelled")
                        break
                    if session.content.strip():
                        if on_progress:
                            on_progress("logs", i + 1, len(sessions), session.window_app)
                        result = await self.analyze_keyboard_log(
                            session.content, window=session.window_app, provider=provider
                        )
                        if result.success:
                            session.analysis = result.content
                            analyzed_count += 1
                results["logs_analyzed"] = analyzed_count

        # Generate reports
        if generate_reports:
            if cancel_event and cancel_event.is_set():
                return results
            if on_progress:
                on_progress("reports", 0, 0, "Generating reports...")
            reports = await self.report_aggregator.generate_reports_for_date(
                date_str,
                generate_summary=self.config.get("reports.daily_summary", True)
            )
            results["reports_generated"] = list(reports.values())

        if on_progress:
            on_progress("done", 0, 0, "Analysis complete")

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
        default="~/opencapture",
        help="Data directory (default: ~/opencapture)"
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

    if args.dir != "~/opencapture":
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
