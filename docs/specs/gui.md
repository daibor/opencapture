# GUI Specification — Cross-Platform System Tray App

## Overview

A cross-platform system tray application providing a graphical interface to OpenCapture. Uses platform-native backends for the best experience on each OS:

- **macOS**: Native PyObjC (NSStatusBar + NSWindow) — no Dock icon
- **Windows/Linux**: pystray (system tray) + tkinter (log window, dialogs)

## Architecture

```
src/opencapture/
├── app.py                    # Thin entry: init_config() → create_app(config).run()
├── gui/
│   ├── __init__.py          # create_app() factory — platform dispatch
│   ├── base.py              # TrayAppBase — shared business logic
│   ├── macos.py             # macOS: PyObjC (NSStatusBar + NSWindow)
│   └── generic.py           # Windows/Linux: pystray + tkinter
```

### TrayAppBase (shared)

All business logic lives in the abstract base class:

- `toggle_capture()` — start/stop with permission checks and error handling
- `request_analysis()` — async analysis with result formatting
- `get_status_text()` — build status line from engine state
- `get_log_path()` — resolve today's log file path
- `shutdown()` — clean shutdown of both engines

Platform backends implement only UI methods:

- `run()` — start event loop
- `on_recording_changed(recording)` — update recording indicator
- `on_analysis_started()` / `on_analysis_complete(msg)` — analysis UI
- `show_alert(title, msg)` — modal dialog
- `refresh_status()` — update status line in menu
- `check_capture_permissions()` — platform permission prompts

## Entry Points

- `opencapture gui` — CLI subcommand
- `opencapture-gui` — Standalone script entry point
- `OpenCapture.app` — PyInstaller bundle (macOS, launches GUI by default)

## Menu Items

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
- **Font**: Monospace (Menlo 12pt on macOS, Consolas 11pt on Windows)
- **Theme**: Dark background (#1e1e1e), light text (#d4d4d4)
- **Behavior**: Read-only, auto-scrolls to bottom on new content

### Content

On open, loads today's existing log file contents. Polls the log file every 0.5s to append new content (tail-like behavior).

### Window Lifecycle

- Close button hides the window (does not destroy)
- Re-opening via menu shows existing window
- Window is not shown on launch (tray icon only)

## Analysis Integration

When "Analyze Today" is clicked:

1. Menu item becomes disabled, status shows "Analyzing..."
2. AnalysisEngine.analyze_today() runs in background thread
3. On completion, callback fires → dispatched to main thread
4. Status line updates with result summary
5. Menu item re-enabled, alert dialog shows result

## Capture Lifecycle

### Start

1. Check permissions via `check_capture_permissions()` (macOS: Accessibility dialog)
2. `CaptureEngine.start()` — creates AutoCapture, starts listeners
3. Recording indicator updated (macOS: title bullet, generic: red tray icon)
4. Menu item label changes to "Stop Capture"

### Stop

1. `CaptureEngine.stop()`
2. Menu item label changes to "Start Capture"
3. Status line shows final stats

## Thread Safety

### macOS Backend

`NSApplication.sharedApplication().run()` drives the NSRunLoop. Engine events fire from background threads; all UI updates are dispatched via `performSelectorOnMainThread:withObject:waitUntilDone:`.

### Generic Backend

pystray runs in a background thread. tkinter runs on the main thread. pystray menu callbacks use `root.after(0, ...)` to dispatch to the tkinter main thread. Analysis callbacks also dispatch via `root.after()`.

## Platform Dependencies

| Platform | Tray | Log Window | Dialogs |
|----------|------|------------|---------|
| macOS | PyObjC NSStatusBar | PyObjC NSWindow | NSAlert |
| Windows | pystray (win32) | tkinter | tkinter messagebox |
| Linux | pystray (GTK) | tkinter | tkinter messagebox |

## PyInstaller Bundles

### macOS (.app)

- Entry point: `packaging/launch_gui.py` → `opencapture.app:main`
- `LSUIElement: true` — menu bar only, no Dock icon
- Bundle ID: `com.opencapture.agent`
- Required permissions: Accessibility, Screen Recording, Microphone

### Windows (.exe)

- Entry point: `opencapture.cli:main` (supports `gui` subcommand)
- Includes pystray + tkinter
- `console=True` for CLI; GUI runs via `opencapture gui`
