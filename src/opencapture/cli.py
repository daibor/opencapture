#!/usr/bin/env python3
"""
OpenCapture CLI - Unified entry point for capture, analysis, and service management.

Supports three install methods:
  1. python run.py           (clone repo)
  2. opencapture              (pip install)
  3. OpenCapture.app          (PyInstaller bundle)
"""

import argparse
import asyncio
import signal
import sys
import textwrap
from pathlib import Path


# ── Service commands ─────────────────────────────────────


def cmd_start():
    """Start capture as a background service."""
    from opencapture.onboarding import is_first_run, mark_setup_complete
    from opencapture.service import get_service_manager

    if is_first_run():
        print()
        print("  OpenCapture")
        print("  Context capture for proactive AI agents.")
        print()
        print("  All data is stored locally in ~/opencapture/")
        print("  AI analysis uses local Ollama by default.")
        print()
        mark_setup_complete()

    mgr = get_service_manager()
    if mgr is None:
        print("Background service is not supported on this platform.")
        print("Run in foreground instead: opencapture")
        return

    print(mgr.start())


def cmd_stop():
    """Stop the background service."""
    from opencapture.service import get_service_manager

    mgr = get_service_manager()
    if mgr is None:
        print("Background service is not supported on this platform.")
        return
    print(mgr.stop())


def cmd_restart():
    """Restart the background service."""
    from opencapture.service import get_service_manager

    mgr = get_service_manager()
    if mgr is None:
        print("Background service is not supported on this platform.")
        return
    print(mgr.restart())


def cmd_status():
    """Show service status and today's stats."""
    from opencapture.date_resolver import DateResolver
    from opencapture.service import get_service_manager

    print()
    print("  OpenCapture")
    print()

    mgr = get_service_manager()
    if mgr:
        st = mgr.status()
        if st.running:
            print(f"  State:      Running (PID {st.pid})")
        else:
            print("  State:      Stopped")
        if hasattr(st, 'auto_start') and st.auto_start:
            print("  Auto-start: Enabled")
    else:
        print("  State:      Unknown (unsupported platform)")

    data_dir = Path.home() / "opencapture"
    print(f"  Data:       {data_dir}")

    today = DateResolver.compute_base_date()
    today_dir = data_dir / today
    if today_dir.exists():
        screenshots = len(list(today_dir.glob("*.webp")))
        logs = len(list(today_dir.glob("*.log")))
        recordings = len(list(today_dir.glob("*.wav")))
        print(f"  Today:      {screenshots} screenshots, {logs} logs, {recordings} recordings")
    else:
        print("  Today:      No data yet")
    print()


def cmd_log(follow: bool = False):
    """Show service logs."""
    from opencapture.service import get_service_manager

    mgr = get_service_manager()
    if mgr is None:
        print("Background service is not supported on this platform.")
        return
    mgr.show_log(follow=follow)


# ── Capture mode ──────────────────────────────────────────


def run_capture(args):
    """Run capture mode via CaptureEngine."""
    from opencapture.config import init_config
    from opencapture.engine import CaptureEngine
    from opencapture.onboarding import cli_onboarding, show_first_session_tip
    from opencapture.platform import get_backend

    # First-run onboarding
    if not cli_onboarding():
        return

    config = init_config(args.config if hasattr(args, "config") else None)
    if args.dir:
        config.set("capture.output_dir", str(Path(args.dir).expanduser()))

    engine = CaptureEngine(config)
    backend = get_backend()

    # Check accessibility before starting
    if not backend.check_accessibility(prompt=False):
        print("[OpenCapture] Requesting Accessibility permission...")
        backend.check_accessibility(prompt=True)
        print("[OpenCapture] Grant access in System Settings -> Accessibility")

        max_wait = 100 if sys.stdout.isatty() else 40
        print("[OpenCapture] Waiting for permission...")

        granted = False
        import time
        for i in range(max_wait):
            time.sleep(3)
            if backend.check_accessibility(prompt=False):
                granted = True
                break
            if i % 10 == 9:
                print("[OpenCapture] Still waiting for permission...")

        if not granted:
            print("[OpenCapture] Permission not granted.")
            sys.exit(1)
        print("[OpenCapture] Accessibility permission granted!")

    # Check screen recording permission
    if not backend.check_screen_recording(prompt=False):
        backend.check_screen_recording(prompt=True)
        print("[OpenCapture] Screen Recording permission is needed for screenshots.")
        print("[OpenCapture] Grant access in System Settings > Privacy & Security > Screen Recording")

    error = engine.start()
    if error:
        print(f"[OpenCapture] Failed to start: {error}")
        sys.exit(1)

    # Handle SIGTERM for clean shutdown (launchctl stop / Windows terminate)
    def handle_term(signum, frame):
        engine.stop()

    signal.signal(signal.SIGTERM, handle_term)
    if sys.platform == "win32":
        try:
            signal.signal(signal.SIGBREAK, handle_term)
        except (AttributeError, OSError):
            pass

    try:
        backend.run_event_loop(lambda: engine.is_running)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()

    # Post-session tip
    show_first_session_tip()


# ── Analysis mode ─────────────────────────────────────────


async def run_analyze(args):
    """Run analysis mode."""
    from opencapture.config import init_config
    from opencapture.analyzer import Analyzer

    config = init_config(args.config)
    if args.dir:
        config.set("capture.output_dir", str(Path(args.dir).expanduser()))

    analyzer = Analyzer(config)

    try:
        await _run_analyze_inner(analyzer, args, config)
    finally:
        await analyzer.close()


async def _run_analyze_inner(analyzer, args, config):
    """Analysis logic (called inside try/finally to ensure cleanup)."""
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

    # Analyze specific date
    from datetime import datetime, timedelta
    from opencapture.date_resolver import DateResolver

    date_str = args.date
    day_start_hour = config.get("capture.day_start_hour", 4)

    if date_str == "today":
        date_str = DateResolver.compute_base_date(day_start_hour=day_start_hour)
    elif date_str == "yesterday":
        today = DateResolver.compute_base_date(day_start_hour=day_start_hour)
        date_str = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    provider = args.provider or config.get_default_provider()

    print(f"Analyzing date: {date_str}")
    print(f"Provider: {provider}")
    print()

    # Confirm before sending data to remote providers
    if not analyzer.confirm_online_usage(args.provider):
        return

    def _print_progress(stage, current, total, detail):
        if total > 0:
            print(f"\r  [{stage}] {current}/{total} {detail}        ", end="", flush=True)
        else:
            print(f"  [{stage}] {detail}")

    results = await analyzer.analyze_day(
        date_str,
        generate_reports=not args.no_reports,
        provider=args.provider,
        on_progress=_print_progress,
    )
    # Clear progress line
    print()

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


# ── Argument parsing ──────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="OpenCapture - Keyboard/Mouse Recording & AI Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Service commands (macOS + Windows):
              opencapture start               Start as background service
              opencapture stop                Stop service
              opencapture restart             Restart service
              opencapture status              Show running state and today's stats
              opencapture log [-f]            Show/follow service logs

            GUI:
              opencapture gui                 Launch system tray app (macOS/Windows)
              opencapture gui --tray          Force cross-platform tray backend

            Examples:
              opencapture                     Start capture (foreground)
              opencapture --analyze today     Analyze today's data
              opencapture --analyze 2026-02-01
              opencapture --provider openai   Use OpenAI for analysis
        """),
    )

    # Service subcommands (positional)
    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "stop", "restart", "status", "log", "gui"],
        default=None,
        help="Service management command",
    )
    parser.add_argument(
        "extra_args",
        nargs="*",
        help=argparse.SUPPRESS,
    )

    # Basic options
    parser.add_argument("-d", "--dir", help="Storage directory (default: ~/opencapture)")
    parser.add_argument("-c", "--config", help="Configuration file path")

    # Analysis mode options
    parser.add_argument(
        "--analyze",
        metavar="DATE",
        nargs="?",
        const="today",
        help="Analysis mode: today, yesterday, or YYYY-MM-DD",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "anthropic", "custom"],
        help="LLM provider",
    )
    parser.add_argument("--no-reports", action="store_true", help="Skip Markdown report generation")

    # Utility options
    parser.add_argument("--health-check", action="store_true", help="Check LLM service status")
    parser.add_argument("--list-dates", action="store_true", help="List available dates")
    parser.add_argument("--check-permission", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check-permission-quiet", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Service management commands
    if args.command == "start":
        cmd_start()
        return
    if args.command == "stop":
        cmd_stop()
        return
    if args.command == "restart":
        cmd_restart()
        return
    if args.command == "status":
        cmd_status()
        return
    if args.command == "log":
        follow = "-f" in args.extra_args
        cmd_log(follow=follow)
        return
    if args.command == "gui":
        if "--tray" in args.extra_args:
            # Force cross-platform tray backend (pystray + tkinter)
            from opencapture.config import init_config
            from opencapture.gui.generic import GenericTrayApp
            config = init_config()
            GenericTrayApp(config).run()
        else:
            from opencapture.app import main as gui_main
            gui_main()
        return

    # Permission check mode
    if args.check_permission:
        from opencapture.platform import get_backend
        backend = get_backend()
        if backend.check_accessibility(prompt=False):
            sys.exit(0)
        backend.check_accessibility(prompt=True)
        sys.exit(1)

    if args.check_permission_quiet:
        from opencapture.platform import get_backend
        sys.exit(0 if get_backend().check_accessibility(prompt=False) else 1)

    # Determine run mode
    if args.analyze or args.health_check or args.list_dates:
        # Analysis mode
        if args.analyze:
            args.date = args.analyze
        asyncio.run(run_analyze(args))
    else:
        # Capture mode (foreground) — via CaptureEngine
        run_capture(args)


if __name__ == "__main__":
    main()
