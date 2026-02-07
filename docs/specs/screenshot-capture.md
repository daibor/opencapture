# Screenshot Capture Specification

## Overview

A screenshot is captured on every mouse action (click, double-click, drag). Each screenshot is a full-screen capture saved as a compressed image, annotated with the active window border and drag overlay when applicable.

## Trigger Rules

Screenshots are triggered on **mouse button release**, not on press. The system distinguishes three action types based on the release event:

### Action Classification

| Action | Condition |
|--------|-----------|
| **click** | Distance between press and release positions <= `drag_threshold` AND not a double-click |
| **dblclick** | Distance between press and release positions <= `drag_threshold` AND time since last click < `double_click_interval` AND distance from last click position < `double_click_distance` |
| **drag** | Distance between press and release positions > `drag_threshold` |

After a double-click is detected, the click history resets to prevent a third click from forming another double-click pair.

### Throttling

A minimum interval of `throttle_ms` must elapse between consecutive captures. Any mouse release event occurring within this interval is silently discarded.

## Screenshot Content

### Full-Screen Capture

Every screenshot captures **all connected monitors** as a single stitched image. Coordinates are adjusted for multi-monitor offsets.

### Active Window Border

A colored rectangle border is drawn around the frontmost application window on the screenshot:

- **Color**: `window_border_color` (RGB)
- **Width**: `window_border_width` pixels
- Windows smaller than 100x100 pixels are ignored (menus, tooltips, etc.)

### Drag Overlay

For drag actions, a semi-transparent rectangle is drawn from the press position to the release position:

- **Fill**: gray (128, 128, 128) at 30% opacity
- **Outline**: dark gray (80, 80, 80) at ~78% opacity, 2px width

## File Naming

Format: `{action}_{HHmmss}_{ms}_{button}_x{X}_y{Y}[_to_x{X2}_y{Y2}].{ext}`

| Component | Description |
|-----------|-------------|
| `action` | One of: `click`, `dblclick`, `drag` |
| `HHmmss` | Time of capture (hours, minutes, seconds) |
| `ms` | Milliseconds (3 digits) |
| `button` | Mouse button name (e.g., `left`, `right`) |
| `x{X}_y{Y}` | Click/press coordinates (absolute screen position) |
| `_to_x{X2}_y{Y2}` | Release coordinates (drag only) |
| `ext` | Image format extension |

Examples:
```
click_143052_789_left_x800_y600.webp
dblclick_143053_012_left_x800_y600.webp
drag_143055_456_left_x100_y200_to_x500_y400.webp
```

## Storage

- **Format**: WebP (lossy)
- **Quality**: `image_quality` (1-100 scale)
- **Location**: `{output_dir}/{YYYY-MM-DD}/{filename}`
- The date directory is created automatically if it does not exist

## Log Entry

Each screenshot generates a log entry in the daily keyboard log file:

```
[HH:MM:SS] 📷 {action} ({x},{y}) {filename}
[HH:MM:SS] 📷 drag ({x1},{y1})->({x2},{y2}) {filename}
```

## Default Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `image_format` | `webp` | Output image format |
| `image_quality` | `80` | Compression quality (1-100) |
| `throttle_ms` | `100` | Minimum interval between captures (ms) |
| `drag_threshold` | `10` | Minimum pixel distance to classify as drag |
| `double_click_interval` | `400` | Maximum time between clicks for double-click (ms) |
| `double_click_distance` | `5` | Maximum pixel distance between clicks for double-click |
| `window_border_color` | `[0, 120, 255]` | Active window border color (RGB) |
| `window_border_width` | `3` | Active window border thickness (px) |

## Concurrency

Each screenshot capture runs in a separate background thread. The main event loop continues processing mouse events without blocking. On shutdown, all pending screenshot threads are joined with a timeout before the process exits.
