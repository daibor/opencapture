# GUI Specification — macOS Menu Bar App

## Overview

A native macOS menu bar application providing a graphical interface to OpenCapture. Built with PyObjC (no additional dependencies). Runs as a status bar item without a Dock icon.

## Entry Points

- `opencapture gui` — CLI subcommand
- `opencapture-gui` — Standalone script entry point
- `OpenCapture.app` — PyInstaller bundle (launches GUI by default)

## Menu Bar

### Status Item

- Position: System menu bar (right side)
- Display: Text title "OC" (no icon file required)
- Click: Opens dropdown menu

### Menu Items

| Item | Action | Notes |
|------|--------|-------|
| **Start Capture** / **Stop Capture** | Toggle capture on/off | Label changes based on state |
| **Show Log** | Open/focus log window | Shows today's activity |
| --- | Separator | |
| **Analyze Today** | Trigger analysis | Disabled while running |
| --- | Separator | |
| *Status line* | Informational | Gray text, e.g. "3 screenshots, 1 recording" |
| **Quit** | Stop capture + quit app | |

## Log Window

### Layout

- **Window**: 700x500, titled "OpenCapture Log", resizable
- **Content**: NSScrollView containing NSTextView
- **Font**: Monospace (Menlo 12pt)
- **Theme**: Dark background (#1e1e1e), light text (#d4d4d4)
- **Behavior**: Read-only, auto-scrolls to bottom on new content

### Content

On open, loads today's existing log file contents. Subsequently appends new events in real-time via engine subscription:

| Event Type | Display Format |
|-----------|---------------|
| `keyboard` | `[HH:MM:SS] ⌨️ {line}` |
| `screenshot` | `[HH:MM:SS] 📷 {action} ({x},{y}) {filename}` |
| `window` | `[HH:MM:SS] 🪟 {app} — {title}` |
| `mic` | `[HH:MM:SS] 🎤 {event_type} {detail}` |
| `status` | `[HH:MM:SS] ℹ️ {message}` |

### Window Lifecycle

- Close button hides the window (does not destroy)
- Re-opening via menu shows existing window
- Window is not shown on launch (menu bar only)

## Analysis Integration

When "Analyze Today" is clicked:

1. Menu item becomes disabled, status line shows "Analyzing..."
2. AnalysisEngine.analyze_today() runs in background thread
3. On completion, callback fires → dispatched to main thread
4. Status line updates with result summary
5. Menu item re-enabled

## Capture Lifecycle

### Start

1. Check accessibility permission via CaptureEngine.check_accessibility()
2. If not granted, show alert dialog with instructions
3. CaptureEngine.start() — creates AutoCapture, starts listeners
4. Menu item label changes to "Stop Capture"
5. Status line updates periodically

### Stop

1. CaptureEngine.stop()
2. Menu item label changes to "Start Capture"
3. Status line shows final stats

## NSRunLoop Integration

`NSApplication.sharedApplication().run()` drives the main thread's NSRunLoop. This is required for:

- WindowTracker: NSWorkspace notifications dispatched on NSOperationQueue.mainQueue()
- Menu bar interaction: NSStatusItem events
- Timer-based status updates

CaptureEngine does NOT own the run loop — the GUI's NSApplication.run() fulfills this role.

## Thread Safety

Engine events fire from background threads (keyboard, mouse, mic). The GUI dispatches all UI updates to the main thread via `performSelectorOnMainThread:withObject:waitUntilDone:`.

## PyInstaller Bundle

When built as OpenCapture.app:

- Entry point: `app.py:main` (GUI by default)
- `LSUIElement: true` — menu bar only, no Dock icon
- Bundle ID: `com.opencapture.agent`
- Required permissions: Accessibility, Screen Recording, Microphone
