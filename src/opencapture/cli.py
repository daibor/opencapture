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
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional


# ── Service management ─────────────────────────────────────
# macOS: launchd (LaunchAgent plist)
# Windows: background subprocess with PID file

PLIST_LABEL = "com.opencapture.agent"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def _log_dir() -> Path:
    d = Path.home() / ".opencapture" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_file() -> Path:
    """PID file for Windows background process."""
    return Path.home() / ".opencapture" / "opencapture.pid"


# ── macOS launchd helpers ──────────────────────────────────

def _get_service_pid_macos() -> Optional[str]:
    """Return PID string if the service is loaded, else None."""
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if PLIST_LABEL in line:
                parts = line.split()
                return parts[0] if parts else None
    except Exception:
        pass
    return None


def _is_service_running_macos() -> bool:
    pid = _get_service_pid_macos()
    return pid is not None and pid != "-"


def _write_plist():
    """Generate LaunchAgent plist pointing to the current Python + cli module."""
    plist_path = _plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir = _log_dir()

    python_exe = sys.executable
    plist_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_exe}</string>
        <string>-m</string>
        <string>opencapture</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_dir}/output.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>"""
    plist_path.write_text(plist_content)


# ── Windows background process helpers ─────────────────────

def _get_service_pid_windows() -> Optional[int]:
    """Return PID if the background process is running, else None."""
    pid_file = _pid_file()
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        # Check if process is alive
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return pid
        # Process not found, clean up stale PID file
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def _is_service_running_windows() -> bool:
    return _get_service_pid_windows() is not None


# ── Cross-platform service commands ───────────────────────

def cmd_start():
    """Start capture as a background service."""
    from opencapture.onboarding import is_first_run, mark_setup_complete

    if is_first_run():
        print()
        print("  OpenCapture")
        print("  Context capture for proactive AI agents.")
        print()
        print("  All data is stored locally in ~/opencapture/")
        print("  AI analysis uses local Ollama by default.")
        print()
        mark_setup_complete()

    if sys.platform == "darwin":
        _cmd_start_macos()
    elif sys.platform == "win32":
        _cmd_start_windows()
    else:
        print("Background service is not supported on this platform.")
        print("Run in foreground instead: opencapture")


def _cmd_start_macos():
    if _is_service_running_macos():
        print(f"  OpenCapture is already running (PID {_get_service_pid_macos()})")
        return

    log_dir = _log_dir()
    for name in ("output.log", "error.log"):
        log_file = log_dir / name
        if log_file.exists():
            log_file.write_text("")

    _write_plist()
    subprocess.run(["launchctl", "load", "-w", str(_plist_path())],
                   capture_output=True)

    import time
    time.sleep(2)

    if _is_service_running_macos():
        print(f"  OpenCapture started (PID {_get_service_pid_macos()})")
        print("  Auto-start on login: enabled")
        print()
        print("  If this is the first run, grant OpenCapture access in:")
        print("  System Settings > Privacy & Security > Accessibility")
    else:
        print("  Failed to start OpenCapture")
        print("  Check logs: opencapture log")


def _cmd_start_windows():
    if _is_service_running_windows():
        pid = _get_service_pid_windows()
        print(f"  OpenCapture is already running (PID {pid})")
        return

    log_dir = _log_dir()
    for name in ("output.log", "error.log"):
        log_file = log_dir / name
        if log_file.exists():
            log_file.write_text("")

    python_exe = sys.executable
    out_log = log_dir / "output.log"
    err_log = log_dir / "error.log"

    # Launch as a detached background process
    import os
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    DETACHED_PROCESS = 0x00000008

    with open(out_log, "w") as stdout_f, open(err_log, "w") as stderr_f:
        proc = subprocess.Popen(
            [python_exe, "-m", "opencapture"],
            stdout=stdout_f,
            stderr=stderr_f,
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

    # Save PID
    pid_file = _pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(proc.pid))

    print(f"  OpenCapture started (PID {proc.pid})")
    print(f"  Logs: {log_dir}")


def cmd_stop():
    """Stop the background service."""
    if sys.platform == "darwin":
        _cmd_stop_macos()
    elif sys.platform == "win32":
        _cmd_stop_windows()
    else:
        print("Background service is not supported on this platform.")


def _cmd_stop_macos():
    plist = _plist_path()
    if not plist.exists():
        print("  OpenCapture is not running")
        return
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    print("  OpenCapture stopped")
    print("  Auto-start on login: disabled")


def _cmd_stop_windows():
    pid = _get_service_pid_windows()
    if pid is None:
        print("  OpenCapture is not running")
        return

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if handle:
            kernel32.TerminateProcess(handle, 0)
            kernel32.CloseHandle(handle)
    except Exception as e:
        print(f"  Failed to stop process: {e}")
        return

    pid_file = _pid_file()
    pid_file.unlink(missing_ok=True)
    print("  OpenCapture stopped")


def cmd_restart():
    """Restart the background service."""
    cmd_stop()
    import time
    time.sleep(1)
    cmd_start()


def cmd_status():
    """Show service status and today's stats."""
    print()
    print("  OpenCapture")
    print()

    if sys.platform == "darwin":
        pid = _get_service_pid_macos()
        if pid and pid != "-":
            print(f"  State:      Running (PID {pid})")
        elif pid:
            print("  State:      Loaded but not running")
        else:
            print("  State:      Stopped")

        plist = _plist_path()
        if plist.exists() and _get_service_pid_macos() is not None:
            print("  Auto-start: Enabled")
        else:
            print("  Auto-start: Disabled")
    elif sys.platform == "win32":
        pid = _get_service_pid_windows()
        if pid:
            print(f"  State:      Running (PID {pid})")
        else:
            print("  State:      Stopped")
    else:
        print("  State:      Unknown (unsupported platform)")

    data_dir = Path.home() / "opencapture"
    print(f"  Data:       {data_dir}")

    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
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
    log_dir = _log_dir()
    out_log = log_dir / "output.log"
    err_log = log_dir / "error.log"

    if not out_log.exists() and not err_log.exists():
        print("  No logs yet. Start the service first: opencapture start")
        return

    if follow:
        if sys.platform == "win32":
            # Windows: use PowerShell Get-Content -Wait
            log_files = []
            if out_log.exists():
                log_files.append(str(out_log))
            if err_log.exists():
                log_files.append(str(err_log))
            if log_files:
                try:
                    subprocess.run(
                        ["powershell", "-Command",
                         f"Get-Content -Path '{log_files[0]}' -Wait -Tail 30"],
                    )
                except KeyboardInterrupt:
                    pass
        else:
            args = ["tail", "-f"]
            if out_log.exists():
                args.append(str(out_log))
            if err_log.exists():
                args.append(str(err_log))
            try:
                subprocess.run(args)
            except KeyboardInterrupt:
                pass
    else:
        if out_log.exists():
            print("  -- Recent output --")
            text = out_log.read_text()
            lines = text.splitlines()[-30:]
            for line in lines:
                print(f"  {line}")
            print()

        if err_log.exists() and err_log.stat().st_size > 0:
            print("  -- Recent errors --")
            text = err_log.read_text()
            lines = text.splitlines()[-10:]
            for line in lines:
                print(f"  {line}")
            print()

        print("  Tip: opencapture log -f to follow in real-time")


# ── Capture mode ──────────────────────────────────────────

def run_capture(args):
    """Run capture mode."""
    from opencapture.auto_capture import AutoCapture
    from opencapture.config import init_config
    from opencapture.onboarding import cli_onboarding, show_first_session_tip

    # First-run onboarding
    if not cli_onboarding():
        return

    config = init_config(args.config if hasattr(args, "config") else None)
    if args.dir:
        config.set("capture.output_dir", str(Path(args.dir).expanduser()))

    capture_config = config.get_capture_config()
    capture = AutoCapture(
        storage_dir=args.dir or config.get("capture.output_dir"),
        mic_enabled=capture_config.get("mic_enabled", False),
        mic_config=capture_config,
    )

    # Handle SIGTERM for clean shutdown (e.g. launchctl stop / Windows terminate)
    def handle_term(signum, frame):
        capture._running = False

    signal.signal(signal.SIGTERM, handle_term)
    if sys.platform == "win32":
        # On Windows, also handle SIGBREAK (Ctrl+Break / process group signal)
        try:
            signal.signal(signal.SIGBREAK, handle_term)
        except (AttributeError, OSError):
            pass
    capture.run()

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
            save_txt=True,
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
        result = await analyzer.analyze_audio(args.audio, save_txt=True)
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
        provider=args.provider,
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
              opencapture --image pic.webp    Analyze single image
              opencapture --audio mic.wav     Transcribe single audio
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
    parser.add_argument("--image", help="Analyze single image")
    parser.add_argument("--audio", help="Transcribe single audio file")
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
        from opencapture.auto_capture import AutoCapture

        if AutoCapture._check_accessibility(prompt=False):
            sys.exit(0)
        AutoCapture._check_accessibility(prompt=True)
        sys.exit(1)

    if args.check_permission_quiet:
        from opencapture.auto_capture import AutoCapture

        sys.exit(0 if AutoCapture._check_accessibility(prompt=False) else 1)

    # Determine run mode
    if args.analyze or args.image or args.audio or args.health_check or args.list_dates:
        # Analysis mode
        if args.analyze:
            args.date = args.analyze
        asyncio.run(run_analyze(args))
    else:
        # Capture mode (foreground)
        run_capture(args)


if __name__ == "__main__":
    main()
