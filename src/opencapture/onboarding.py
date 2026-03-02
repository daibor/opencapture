"""
First-run onboarding for OpenCapture.

Detects first run via a marker file and provides platform-appropriate
welcome messages, permission guidance, and privacy notices.
"""

import sys
from pathlib import Path
from typing import Optional


_MARKER_FILE = ".setup_complete"
_CONFIG_DIR = Path.home() / ".opencapture"


def is_first_run() -> bool:
    """Check if this is the first time OpenCapture is running."""
    return not (_CONFIG_DIR / _MARKER_FILE).exists()


def mark_setup_complete():
    """Mark first-run setup as complete."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (_CONFIG_DIR / _MARKER_FILE).touch()


# ── CLI onboarding ────────────────────────────────────────

_WELCOME = """\
  OpenCapture
  Context capture for proactive AI agents.

  OpenCapture records keyboard, mouse, screenshots, and audio
  in the background to build rich context for AI analysis.
  All data stays on your machine by default.
"""

_PRIVACY_NOTICE = """\
  Privacy
    - All data is stored locally in ~/opencapture/
    - AI analysis uses local Ollama by default
    - Remote providers (OpenAI, Anthropic) require explicit opt-in
    - No telemetry or analytics data is sent anywhere
"""

_MACOS_PERMISSIONS = """\
  Permissions needed (macOS)
    OpenCapture needs the following permissions in
    System Settings > Privacy & Security:

    1. Accessibility    - monitors keyboard and mouse activity
    2. Screen Recording - captures screenshots on click events
    3. Microphone       - records audio (optional, off by default)

    macOS will prompt you to grant each permission on first use.
"""

_WINDOWS_INFO = """\
  Platform notes (Windows)
    No special permissions are required on Windows.
    Keyboard and mouse monitoring works out of the box.
"""

_QUICK_START = """\
  Quick start
    opencapture              Start capture (foreground)
    opencapture gui          Launch system tray GUI
    opencapture start        Run as background service
    opencapture --analyze today   Analyze today's data
    opencapture --help       Show all options
"""


def cli_onboarding() -> bool:
    """Show CLI first-run onboarding. Returns True if user wants to proceed."""
    if not is_first_run():
        return True

    print()
    print(_WELCOME)
    print(_PRIVACY_NOTICE)

    if sys.platform == "darwin":
        print(_MACOS_PERMISSIONS)
    elif sys.platform == "win32":
        print(_WINDOWS_INFO)

    print(_QUICK_START)

    # Non-interactive mode (piped stdin, background service) — skip prompt
    if not sys.stdin.isatty():
        mark_setup_complete()
        return True

    try:
        answer = input("  Ready to start? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer in ("", "y", "yes"):
        mark_setup_complete()
        return True

    print("  Run `opencapture` again when you're ready.")
    return False


# ── GUI onboarding messages ───────────────────────────────

_GUI_WELCOME = (
    "Welcome to OpenCapture!\n\n"
    "OpenCapture records your keyboard, mouse, and screen activity "
    "in the background to build context for AI analysis.\n\n"
    "All data stays on your machine by default."
)

_PERMISSION_MESSAGES = {
    "accessibility": (
        "Accessibility Permission Required",
        "OpenCapture needs Accessibility access to monitor keyboard "
        "and mouse activity. This lets it understand what you're working on.\n\n"
        "Grant access in:\n"
        "System Settings > Privacy & Security > Accessibility",
    ),
    "screen_recording": (
        "Screen Recording Permission",
        "Screen Recording access lets OpenCapture capture screenshots "
        "when you click, creating visual context of your workflow.\n\n"
        "Grant access in:\n"
        "System Settings > Privacy & Security > Screen Recording",
    ),
    "microphone": (
        "Microphone Permission (Optional)",
        "Microphone access is optional. When enabled, OpenCapture "
        "records audio from video calls to include in your activity context.\n\n"
        "You can enable this later in config: mic_enabled: true",
    ),
}

_SETUP_COMPLETE_MSG = (
    "You're all set!",
    "OpenCapture is ready. Click 'Start Capture' to begin recording.\n\n"
    "Tip: Your data is stored in ~/opencapture/ and analyzed locally with Ollama.",
)


def get_gui_welcome() -> str:
    """Get welcome message for GUI first-run."""
    return _GUI_WELCOME


def get_permission_message(permission: str) -> tuple[str, str]:
    """Get (title, body) for a permission request dialog."""
    return _PERMISSION_MESSAGES.get(permission, ("Permission Required", ""))


def get_setup_complete_message() -> tuple[str, str]:
    """Get (title, body) for the setup-complete dialog."""
    return _SETUP_COMPLETE_MSG


# ── Post-session tips ─────────────────────────────────────

_FIRST_SESSION_TIP = (
    "\n  Tip: Your first session is recorded!"
    "\n  Run `opencapture --analyze today` to see AI analysis."
    "\n  Reports are saved to ~/opencapture/reports/\n"
)


def show_first_session_tip():
    """Show a tip after the first capture session ends."""
    marker = _CONFIG_DIR / ".first_session_done"
    if marker.exists():
        return
    print(_FIRST_SESSION_TIP)
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    marker.touch()
