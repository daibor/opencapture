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

### Application Switch Detection

Application switches are detected via macOS `NSWorkspaceDidActivateApplicationNotification`. This fires whenever a different application becomes the frontmost app.

### Window Title Detection

Window titles are retrieved through the macOS Accessibility API:

1. Get the focused window of the frontmost application
2. Read its `AXTitle` attribute
3. If no focused window exists, fall back to the first window in the window list

### Per-Keypress Polling

In addition to notification-based detection, every keypress triggers a fresh check of the active window info. This catches in-app window/tab switches that do not generate an application activation notification (e.g., switching tabs in a browser or switching files in an editor).

## Change Detection

A window change is considered to have occurred when **either** the app name or the window title differs from the previously recorded values. Bundle ID changes alone do not trigger a new context block (they always accompany app name changes).

## Usage by Other Components

- **Keyboard Logger**: Window changes trigger a flush of the current keystroke line and insertion of a new block header in the log file (see keyboard-logging spec)
- **Screenshot Capture**: The active window bounds are used to draw the highlight border on screenshots (see screenshot-capture spec)

## macOS Requirements

- **Accessibility permission**: Required for reading window titles via the Accessibility API. Must be granted in System Settings > Privacy & Security > Accessibility.
- **Screen Recording permission**: Required for screenshot capture and window enumeration. Must be granted in System Settings > Privacy & Security > Screen Recording.
