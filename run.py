#!/usr/bin/env python3
"""
OpenCapture Main Entry Point
Supports capture mode and analysis mode
"""

import argparse
import asyncio
import sys
from pathlib import Path


def run_capture(args):
    """Run capture mode"""
    from src.auto_capture import AutoCapture
    from src.config import init_config

    config = init_config(args.config if hasattr(args, 'config') else None)
    if args.dir:
        config.set("capture.output_dir", str(Path(args.dir).expanduser()))

    capture_config = config.get_capture_config()
    capture = AutoCapture(
        storage_dir=args.dir or config.get("capture.output_dir"),
        mic_enabled=capture_config.get("mic_enabled", False),
        mic_config=capture_config,
    )
    capture.run()


async def run_analyze(args):
    """Run analysis mode"""
    from src.config import init_config
    from src.analyzer import Analyzer

    config = init_config(args.config)
    if args.dir:
        config.set("capture.output_dir", str(Path(args.dir).expanduser()))

    analyzer = Analyzer(config)

    # Health check
    if args.health_check:
        print("Checking LLM services...")
        status = await analyzer.health_check()
        all_ok = True
        for provider, ok in status.items():
            icon = "OK" if ok else "FAIL"
            print(f"  [{icon}] {provider}")
            if not ok:
                all_ok = False
        if not all_ok:
            print()
            await analyzer.preflight_check(args.provider)
        return

    # List dates
    if args.list_dates:
        print("Available dates:")
        for date in analyzer.list_available_dates():
            print(f"  - {date}")
        return

    # Analyze single image
    if args.image:
        if not await analyzer.preflight_check(args.provider):
            return
        if not analyzer.confirm_online_usage(args.provider):
            return
        print(f"Analyzing image: {args.image}")
        result = await analyzer.analyze_image(
            args.image,
            provider=args.provider,
            save_txt=True
        )
        if result.success:
            print(f"\n{result.content}")
            print(f"\n[Time: {result.inference_time:.2f}s]")
        else:
            print(f"Error: {result.error}")
        return

    # Transcribe single audio
    if args.audio:
        print(f"Transcribing audio: {args.audio}")
        result = await analyzer.analyze_audio(
            args.audio,
            save_txt=True
        )
        if result.success:
            print(f"\n{result.content}")
            print(f"\n[Time: {result.inference_time:.2f}s]")
        else:
            print(f"Error: {result.error}")
        return

    # Analyze specific date
    from datetime import datetime, timedelta
    date_str = args.date

    if date_str == "today":
        date_str = datetime.now().strftime("%Y-%m-%d")
    elif date_str == "yesterday":
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    provider = args.provider or config.get_default_provider()

    print(f"Analyzing date: {date_str}")
    print(f"Provider: {provider}")
    print()

    # Confirm before sending data to remote providers
    if not analyzer.confirm_online_usage(args.provider):
        return

    results = await analyzer.analyze_day(
        date_str,
        generate_reports=not args.no_reports,
        provider=args.provider
    )

    if "error" in results:
        print(f"Error: {results['error']}")

        # Show available dates
        dates = analyzer.list_available_dates()
        if dates:
            print("\nAvailable dates:")
            for d in dates[:5]:
                print(f"  - {d}")
        return

    print("=" * 50)
    print("Analysis Complete")
    print("=" * 50)
    print(f"Images analyzed: {results.get('images_analyzed', 0)}")
    print(f"Audios transcribed: {results.get('audios_transcribed', 0)}")
    print(f"Logs parsed: {results.get('logs_analyzed', 0)}")

    if results.get("reports_generated"):
        print("\nGenerated reports:")
        for report in results["reports_generated"]:
            print(f"  - {report}")


def main():
    parser = argparse.ArgumentParser(
        description="OpenCapture - Keyboard/Mouse Recording & AI Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Start capture
  %(prog)s --analyze today      # Analyze today's data
  %(prog)s --analyze 2026-02-01 # Analyze specific date
  %(prog)s --image pic.webp     # Analyze single image
  %(prog)s --audio mic.wav      # Transcribe single audio
  %(prog)s --provider openai    # Use OpenAI for analysis
"""
    )

    # Basic options
    parser.add_argument(
        "-d", "--dir",
        help="Storage directory (default: ~/auto-capture)"
    )
    parser.add_argument(
        "-c", "--config",
        help="Configuration file path"
    )

    # Analysis mode options
    parser.add_argument(
        "--analyze",
        metavar="DATE",
        nargs="?",
        const="today",
        help="Analysis mode: today, yesterday, or YYYY-MM-DD"
    )
    parser.add_argument(
        "--image",
        help="Analyze single image"
    )
    parser.add_argument(
        "--audio",
        help="Transcribe single audio file"
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "anthropic", "custom"],
        help="LLM provider"
    )
    parser.add_argument(
        "--no-reports",
        action="store_true",
        help="Skip Markdown report generation"
    )

    # Utility options
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

    # Determine run mode
    if args.analyze or args.image or args.audio or args.health_check or args.list_dates:
        # Analysis mode
        if args.analyze:
            args.date = args.analyze
        asyncio.run(run_analyze(args))
    else:
        # Capture mode
        run_capture(args)


if __name__ == "__main__":
    main()
