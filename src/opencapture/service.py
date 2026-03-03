"""
Service management abstraction — background capture as a system service.

Provides a unified interface for starting/stopping the capture daemon,
with platform-specific backends:
  - macOS: launchd (LaunchAgent plist)
  - Windows: detached background process with PID file
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PLIST_LABEL = "com.opencapture.agent"


@dataclass
class ServiceStatus:
    """Service state snapshot."""
    running: bool
    pid: Optional[str] = None
    auto_start: bool = False


class ServiceManager(ABC):
    """Abstract service lifecycle manager."""

    @property
    def log_dir(self) -> Path:
        d = Path.home() / ".opencapture" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _clear_logs(self):
        for name in ("output.log", "error.log"):
            log_file = self.log_dir / name
            if log_file.exists():
                log_file.write_text("")

    @abstractmethod
    def start(self) -> str:
        """Start the service. Returns a human-readable status message."""

    @abstractmethod
    def stop(self) -> str:
        """Stop the service. Returns a human-readable status message."""

    def restart(self) -> str:
        """Restart the service."""
        self.stop()
        import time
        time.sleep(1)
        return self.start()

    @abstractmethod
    def status(self) -> ServiceStatus:
        """Return current service status."""

    @abstractmethod
    def show_log(self, follow: bool = False):
        """Display service logs. If follow=True, stream in real-time."""


class LaunchdManager(ServiceManager):
    """macOS launchd service manager."""

    @property
    def _plist_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

    def _get_pid(self) -> Optional[str]:
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

    def _write_plist(self):
        plist_path = self._plist_path
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        log_dir = self.log_dir

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

    def start(self) -> str:
        pid = self._get_pid()
        if pid and pid != "-":
            return f"  OpenCapture is already running (PID {pid})"

        self._clear_logs()
        self._write_plist()
        subprocess.run(["launchctl", "load", "-w", str(self._plist_path)],
                       capture_output=True)

        import time
        time.sleep(2)

        pid = self._get_pid()
        if pid and pid != "-":
            return (
                f"  OpenCapture started (PID {pid})\n"
                f"  Auto-start on login: enabled\n"
                f"\n"
                f"  If this is the first run, grant OpenCapture access in:\n"
                f"  System Settings > Privacy & Security > Accessibility"
            )
        return "  Failed to start OpenCapture\n  Check logs: opencapture log"

    def stop(self) -> str:
        plist = self._plist_path
        if not plist.exists():
            return "  OpenCapture is not running"
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        return "  OpenCapture stopped\n  Auto-start on login: disabled"

    def status(self) -> ServiceStatus:
        pid = self._get_pid()
        running = pid is not None and pid != "-"
        auto_start = self._plist_path.exists() and pid is not None
        return ServiceStatus(running=running, pid=pid if running else None, auto_start=auto_start)

    def show_log(self, follow: bool = False):
        out_log = self.log_dir / "output.log"
        err_log = self.log_dir / "error.log"

        if not out_log.exists() and not err_log.exists():
            print("  No logs yet. Start the service first: opencapture start")
            return

        if follow:
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
            self._print_recent_logs(out_log, err_log)

    def _print_recent_logs(self, out_log: Path, err_log: Path):
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


class ProcessManager(ServiceManager):
    """Windows background process manager using PID file."""

    @property
    def _pid_file(self) -> Path:
        return Path.home() / ".opencapture" / "opencapture.pid"

    def _get_pid(self) -> Optional[int]:
        pid_file = self._pid_file
        if not pid_file.exists():
            return None
        try:
            pid = int(pid_file.read_text().strip())
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return pid
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        return None

    def start(self) -> str:
        pid = self._get_pid()
        if pid is not None:
            return f"  OpenCapture is already running (PID {pid})"

        self._clear_logs()

        import os
        python_exe = sys.executable
        out_log = self.log_dir / "output.log"
        err_log = self.log_dir / "error.log"

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

        self._pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._pid_file.write_text(str(proc.pid))
        return f"  OpenCapture started (PID {proc.pid})\n  Logs: {self.log_dir}"

    def stop(self) -> str:
        pid = self._get_pid()
        if pid is None:
            return "  OpenCapture is not running"

        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
            if handle:
                kernel32.TerminateProcess(handle, 0)
                kernel32.CloseHandle(handle)
        except Exception as e:
            return f"  Failed to stop process: {e}"

        self._pid_file.unlink(missing_ok=True)
        return "  OpenCapture stopped"

    def status(self) -> ServiceStatus:
        pid = self._get_pid()
        return ServiceStatus(running=pid is not None, pid=str(pid) if pid else None)

    def show_log(self, follow: bool = False):
        out_log = self.log_dir / "output.log"
        err_log = self.log_dir / "error.log"

        if not out_log.exists() and not err_log.exists():
            print("  No logs yet. Start the service first: opencapture start")
            return

        if follow:
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


def get_service_manager() -> Optional[ServiceManager]:
    """Return the platform-appropriate ServiceManager, or None if unsupported."""
    if sys.platform == "darwin":
        return LaunchdManager()
    elif sys.platform == "win32":
        return ProcessManager()
    return None
