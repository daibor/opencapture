# Startup & Launch Specification

## Overview

OpenCapture runs as a macOS background service via LaunchAgent. To appear as a recognizable application in macOS permission dialogs (Accessibility, Screen Recording), the Python process is launched from a minimal `.app` bundle using a compiled native wrapper. This specification covers the `.app` bundle structure, LaunchAgent configuration, permission flow, and CLI lifecycle commands.

## App Bundle

A headless `.app` bundle is generated locally by the installer. It is not code-signed with a developer certificate — ad-hoc signing is sufficient for local TCC (Transparency, Consent, and Control) recognition.

### Directory Structure

```
~/.opencapture/OpenCapture.app/
  Contents/
    Info.plist
    MacOS/
      OpenCapture           # compiled C wrapper (CFBundleExecutable)
      python3               # copy of venv Python binary
```

### Info.plist

| Key | Value | Purpose |
|-----|-------|---------|
| **CFBundleIdentifier** | `com.opencapture.agent` | TCC database key, matches LaunchAgent label |
| **CFBundleName** | `OpenCapture` | Display name in System Settings |
| **CFBundleDisplayName** | `OpenCapture` | User-visible name |
| **CFBundleExecutable** | `OpenCapture` | Entry point in `Contents/MacOS/` |
| **CFBundlePackageType** | `APPL` | Standard application type |
| **LSUIElement** | `true` | No Dock icon, but allows permission dialogs |

### Native Wrapper + In-Bundle Python

macOS Accessibility TCC checks the **calling process's code identity**, not the parent process. So the Python binary must live inside the `.app` bundle for TCC to attribute permission requests to "OpenCapture".

`Contents/MacOS/OpenCapture` is a compiled C wrapper that:

1. Sets `PYTHONHOME` (base Python prefix, for stdlib) and `PYTHONPATH` (install dir + venv site-packages)
2. Sets `PYTHONUNBUFFERED=1`
3. **exec**s the in-bundle `python3` with `run.py`

After `exec`, the process IS `python3` from within the `.app` bundle. macOS sees the executable path is inside `OpenCapture.app/Contents/MacOS/` and attributes it to `com.opencapture.agent`. This means:

- **"OpenCapture"** appears in System Settings permission lists
- Users can find and toggle the permission without manually adding executables
- `AXIsProcessTrusted()` correctly returns `true` after the user grants access

`Contents/MacOS/python3` is a copy of the venv Python binary. It uses absolute paths for its dylib references (Homebrew Python), so the copy works without additional framework bundling.

The C wrapper is compiled during installation with `cc -O2` (requires Xcode Command Line Tools, which Homebrew already depends on). Python paths are embedded at compile time.

**Why not fork?** The fork approach (parent stays alive, child exec's Python) doesn't work for Accessibility. macOS Accessibility checks the calling process's own code identity, not the "responsible process". Only Screen Recording and Microphone use the responsible-process mechanism.

### Code Signing

After creation, the bundle is ad-hoc signed:

```
codesign --force --sign - ~/.opencapture/OpenCapture.app
```

This gives the bundle a code identity that macOS TCC can reference without requiring an Apple Developer certificate.

## LaunchAgent

### Plist Configuration

Installed at `~/Library/LaunchAgents/com.opencapture.agent.plist`.

| Key | Value | Purpose |
|-----|-------|---------|
| **Label** | `com.opencapture.agent` | Unique service identifier |
| **ProgramArguments** | `[.app/Contents/MacOS/OpenCapture]` | Launches via `.app` bundle |
| **WorkingDirectory** | `~/.opencapture` | Ensures relative paths resolve |
| **RunAtLoad** | `true` | Starts automatically on login |
| **KeepAlive** | `false` | Does not auto-restart on crash |
| **StandardOutPath** | `~/.opencapture/logs/output.log` | Stdout capture |
| **StandardErrorPath** | `~/.opencapture/logs/error.log` | Stderr capture |
| **PYTHONUNBUFFERED** | `1` | Disables output buffering for real-time logs |

### Why PYTHONUNBUFFERED

When Python writes to a file (not a terminal), stdout is fully buffered. Without this flag, log output stays in memory and is lost if the process crashes — making debugging impossible. This is set both in the plist EnvironmentVariables and in the native wrapper via `setenv()`.

## Permission Flow

### Required Permissions

| Permission | Purpose | System Settings Path |
|------------|---------|---------------------|
| **Accessibility** | Keyboard logging, window title reading | Privacy & Security → Accessibility |
| **Screen Recording** | Screenshot capture | Privacy & Security → Screen Recording |
| **Microphone** | Audio recording (if enabled) | Privacy & Security → Microphone |

### First-Run Flow

1. User runs `opencapture start`
2. LaunchAgent starts `.app/Contents/MacOS/OpenCapture` (native wrapper)
3. Wrapper forks → child Python calls `AXIsProcessTrustedWithOptions` with prompt option
4. macOS shows permission dialog identifying **"OpenCapture"** (via TCC responsible process)
5. User opens System Settings → "OpenCapture" appears in Accessibility list
6. Python waits up to 2 minutes for permission to be granted
7. Once granted, capture begins

### Background Service Behavior

When launched by `launchd` (non-interactive), if permissions are missing:
- Triggers permission dialog (attributed to "OpenCapture")
- Waits up to 2 minutes for user to grant
- Logs status messages to `~/.opencapture/logs/output.log`
- Exits with code 1 if not granted within timeout

### Interactive Mode Behavior

When run in foreground (`opencapture run`), if permissions are missing:
- Triggers permission dialog
- Waits up to 5 minutes for user to grant
- Prints periodic status messages to terminal

## CLI Commands

All commands are provided by the `opencapture` launcher script at `~/.local/bin/opencapture`.

### Service Commands

| Command | Description |
|---------|-------------|
| `opencapture start` | Start LaunchAgent (permissions handled by the service) |
| `opencapture stop` | Unload LaunchAgent |
| `opencapture restart` | Stop + start |
| `opencapture status` | Show running state, PID, today's stats |
| `opencapture log [-f]` | Show recent logs (`-f` for real-time follow) |
| `opencapture run` | Foreground mode (for debugging) |

### Start Sequence

```
opencapture start
  ├─ is_service_running? → "already running" and return
  ├─ .app executable exists? → error if missing
  ├─ Clear logs
  ├─ Generate/update LaunchAgent plist
  ├─ launchctl load -w
  └─ Verify running after 2s
```

### Stop Sequence

```
opencapture stop
  └─ launchctl unload plist
```

## Default Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Install directory | `~/.opencapture` | Application files and venv |
| Data directory | `~/opencapture` | Captured screenshots, logs, recordings |
| Log directory | `~/.opencapture/logs` | Service stdout/stderr logs |
| LaunchAgent label | `com.opencapture.agent` | launchd service identifier |
| Bundle ID | `com.opencapture.agent` | macOS TCC identifier |
| Permission wait (background) | 2 minutes | How long the service waits for permission |
| Permission wait (interactive) | 5 minutes | How long foreground mode waits |
| Service start verify | 2 seconds | How long `start` waits to verify the process launched |
