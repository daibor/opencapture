---
name: opencapture
description: Desktop activity recorder & AI analyzer. Records keyboard, mouse, screenshots, and microphone audio on macOS. Analyzes captured data with local or remote LLMs to generate daily activity reports.
homepage: https://github.com/daibor/opencapture
user-invocable: true
metadata: {"openclaw":{"os":["darwin"],"requires":{"bins":["opencapture"]},"emoji":"📸"}}
---

# OpenCapture — Desktop Activity Capture & Analysis

OpenCapture is a macOS tool that runs as a background service, recording keyboard input, mouse clicks (with screenshots), active window changes, and optionally microphone audio. It stores everything locally and can analyze captured data using LLMs (local Ollama or remote APIs) to produce Markdown activity reports.

## Commands

All commands use the `opencapture` CLI installed at `~/.local/bin/opencapture`.

### Service Control

```bash
# Start recording as a background service (auto-runs on login)
opencapture start

# Stop recording
opencapture stop

# Restart service
opencapture restart

# Show running state, auto-start status, and today's capture stats
opencapture status
```

### Analysis

Analysis requires an LLM provider. Default is local Ollama. Remote providers (OpenAI, Anthropic) require API keys and `privacy.allow_online: true` in config.

```bash
# Analyze a specific day's data and generate reports
opencapture analyze today
opencapture analyze yesterday
opencapture analyze 2026-02-01

# Use a specific LLM provider
opencapture analyze today --provider openai
opencapture analyze today --provider anthropic

# Analyze without generating report files
opencapture analyze today --no-reports

# Analyze a single screenshot
opencapture image ~/opencapture/2026-02-08/click_143052_123_left_x500_y300.webp

# Transcribe a single audio recording
opencapture audio ~/opencapture/2026-02-08/mic_100530_456_zoom_dur45.wav
```

### Utilities

```bash
# List dates that have captured data
opencapture list-dates

# Check LLM provider health (Ollama running? API keys valid?)
opencapture health-check

# View service logs
opencapture log          # last 30 lines
opencapture log -f       # follow in real-time
```

## Data Locations

| Path | Content |
|------|---------|
| `~/opencapture/YYYY-MM-DD/` | Daily capture directory |
| `~/opencapture/YYYY-MM-DD/YYYY-MM-DD.log` | Unified activity log |
| `~/opencapture/YYYY-MM-DD/*.webp` | Click/drag screenshots |
| `~/opencapture/YYYY-MM-DD/*.wav` | Microphone recordings |
| `~/opencapture/YYYY-MM-DD/*.txt` | Per-file AI analysis results |
| `~/opencapture/reports/YYYY-MM-DD.md` | Daily activity report |
| `~/opencapture/reports/YYYY-MM-DD_images.md` | Detailed image analysis report |
| `~/.opencapture/config.yaml` | Configuration file |

## Log Format

The `.log` file uses window-grouped blocks separated by triple newlines. Each block starts with an app header:

```
[2026-02-08 14:30:52] Chrome | GitHub - Pull Requests (com.google.Chrome)
[14:30:52] ⌨️ typed search query and pressed enter
[14:30:55] 📷 click (500, 300) click_143055_123_left_x500_y300.webp
[14:31:10] 📷 drag (100, 200)->(400, 500) drag_143110_456_left_x100_y200_to_x400_y500.webp

[2026-02-08 14:35:00] 🎤 mic_start | Zoom (us.zoom.xos)
[2026-02-08 14:40:00] 🎤 mic_stop (300s) mic_143500_789_zoom_dur300.wav
```

## Reading Reports

After running `opencapture analyze`, read the generated Markdown report to summarize the user's day:

```bash
cat ~/opencapture/reports/2026-02-08.md
```

## When to Use

- User asks "what did I do today" or "summarize my day" — run `opencapture analyze today`, then read the report
- User asks about their productivity or work patterns — analyze recent dates and compare
- User wants to check if recording is active — run `opencapture status`
- User wants to start/stop recording — use `opencapture start` / `opencapture stop`
- User asks about a specific screenshot or moment — list files in the date directory, then analyze specific images
- User asks to transcribe a meeting/call — find the `.wav` file and run `opencapture audio <path>`

## Configuration

Edit `~/.opencapture/config.yaml` to change settings. Key options:

- `capture.mic_enabled: true` — enable microphone recording
- `llm.default_provider` — set default LLM (ollama/openai/anthropic)
- `privacy.allow_online: true` — required for remote API providers
- `llm.openai.api_key` / `llm.anthropic.api_key` — API credentials

## Notes

- OpenCapture requires macOS Accessibility and Screen Recording permissions. On first `opencapture start`, grant access in System Settings > Privacy & Security.
- All data stays local by default. Remote LLM providers must be explicitly enabled.
- The service auto-starts on login when started via `opencapture start`.
- Screenshots are WebP format with the active window highlighted by a blue border.
