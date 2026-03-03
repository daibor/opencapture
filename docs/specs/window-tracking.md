# Window Tracking Specification

## Overview

The active window (frontmost application) is continuously tracked to provide context for all captured events. Window information is used by both the keyboard logger and the screenshot capturer.

## Tracked Information

For each active window, three properties are recorded:

| Property | Description | Example |
|----------|-------------|---------|
| **App Name** | Localized application name | `VSCode`, `Safari`, `Terminal` |
| **Window Title** | Title of the focused window | `main.py`, `Google - Search`, `bash` |
| **Bundle ID** | macOS application bundle identifier | `com.microsoft.VSCode`, `com.apple.Safari` |

## Detection Methods

Window tracking is handled by the platform backend (`PlatformBackend.start_window_observer()`). The backend calls a callback with `(app_name, window_title, bundle_id)` whenever the active window changes.

### macOS (MacOSBackend)

- **Application switches**: Detected via `NSWorkspaceDidActivateApplicationNotification`
- **Window titles**: Retrieved through the Accessibility API (`AXTitle` attribute)
- **Fallback**: If no focused window exists, falls back to the first window in the window list

### Windows (WindowsBackend)

- **Polling-based**: A background thread polls `GetForegroundWindow()` at regular intervals
- **Window titles**: Retrieved via `GetWindowTextW()`
- **Process info**: PID → executable path via `GetModuleFileNameExW()`

### Per-Keypress Polling

In addition to observer-based detection, every keypress triggers a fresh check of the active window info via `get_backend().get_active_window_info()`. This catches in-app window/tab switches that do not generate an application activation notification (e.g., switching tabs in a browser or switching files in an editor).

## Change Detection

A window change is considered to have occurred when **either** the app name or the window title differs from the previously recorded values. Bundle ID changes alone do not trigger a new context block (they always accompany app name changes).

## Usage by Other Components

- **Keyboard Logger**: Window changes trigger a flush of the current keystroke line and insertion of a new block header in the log file (see keyboard-logging spec)
- **Screenshot Capture**: The active window bounds are used to draw the highlight border on screenshots (see screenshot-capture spec)

## Platform Requirements

### macOS
- **Accessibility permission**: Required for reading window titles via the Accessibility API. Must be granted in System Settings > Privacy & Security > Accessibility.
- **Screen Recording permission**: Required for screenshot capture and window enumeration. Must be granted in System Settings > Privacy & Security > Screen Recording.

### Windows
- No special permissions required for window tracking.
