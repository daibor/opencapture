# Keyboard Logging Specification

## Overview

All keyboard input is captured and written to a daily log file. Keystrokes are grouped by time clusters and organized by active window context.

## Log File

- **Path**: `{output_dir}/{YYYY-MM-DD}/{YYYY-MM-DD}.log`
- **Encoding**: UTF-8
- The same log file also contains screenshot log entries (see screenshot-capture spec) and microphone log entries (see microphone-capture spec)

## Window Context Blocks

The log is divided into blocks separated by **triple newlines** (`\n\n\n`). Each block represents a window context session.

### Block Header

When the active window changes (different app name or window title), a new block begins with a header line:

```
[YYYY-MM-DD HH:MM:SS] AppName | WindowTitle (bundle_id)
[YYYY-MM-DD HH:MM:SS] AppName (bundle_id)
```

The second format (without window title) is used when the window title is empty.

### Window Change Detection

A window change is detected on every keypress by comparing the current frontmost application's name and window title against the previously recorded values. If either differs, the current line is flushed and a new block header is written.

## Time Clustering

Keystrokes are grouped into lines based on temporal proximity:

- **Cluster interval**: `cluster_interval` seconds (default: 20)
- If the gap between two consecutive keypresses exceeds the cluster interval, the current line is flushed and a new line begins
- Each line is prefixed with the timestamp of its **first** keystroke

### Line Format

```
[YYYY-MM-DD HH:MM:SS] {accumulated_characters}
```

## Key Representation

### Printable Characters

Regular characters are recorded as-is (e.g., `a`, `B`, `1`, `@`).

### Special Keys

Special key symbols are provided by the platform backend via `get_backend().get_key_symbols()`. This allows each platform to use its native conventions:

#### macOS Symbols (default)

| Key | Symbol | Key | Symbol |
|-----|--------|-----|--------|
| Enter/Return | `↩` | Backspace | `⌫` |
| Tab | `⇥` | Delete (Forward) | `⌦` |
| Space | ` ` (literal space) | Escape | `⎋` |
| Shift (L/R) | `⇧` | Control (L/R) | `⌃` |
| Option/Alt (L/R) | `⌥` | Command (L/R) | `⌘` |
| Caps Lock | `⇪` | | |
| Up | `↑` | Down | `↓` |
| Left | `←` | Right | `→` |
| Home | `↖` | End | `↘` |
| Page Up | `⇞` | Page Down | `⇟` |
| F1-F12 | `F1`-`F12` | | |

#### Windows Labels

On Windows, modifier keys use text labels instead of Unicode symbols:

| Key | Label | Key | Label |
|-----|-------|-----|-------|
| Ctrl (L/R) | `Ctrl` | Alt (L/R) | `Alt` |
| Win (L/R) | `Win` | Shift (L/R) | `Shift` |

Other special keys use the same Unicode symbols as macOS.

### Unknown Keys

Keys not in the mapping are recorded as `[{key}]` (e.g., `[Key.media_play_pause]`).

## Log File Example

```


[2026-02-05 10:30:45] VSCode | main.py (com.microsoft.VSCode)
[2026-02-05 10:30:45] def hello():
[2026-02-05 10:30:47]     print("world")↩
[10:30:52] 📷 click (800,600) click_103052_123_left_x800_y600.webp


[2026-02-05 10:31:10] Terminal | bash (com.apple.Terminal)
[2026-02-05 10:31:10] python main.py↩
```

## Flush Rules

The keystroke buffer is flushed (written to disk) when any of these occur:

1. A window change is detected
2. The time gap between keypresses exceeds the cluster interval
3. The system receives a shutdown signal (graceful stop)
4. A forced flush is explicitly requested

## Default Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cluster_interval` | `20` | Seconds of inactivity before starting a new line |

## Thread Safety

All log writes are protected by a mutex lock. The keyboard listener callback and screenshot log writer share the same lock to prevent interleaved writes.
