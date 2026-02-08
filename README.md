# OpenCapture

[![PyPI](https://img.shields.io/pypi/v/opencapture)](https://pypi.org/project/opencapture/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

[中文文档](README_zh.md)

Automatic screenshot + AI understanding tool for macOS. Records keyboard input, mouse actions, microphone audio, and uses AI to analyze everything.

## Features

- **Keyboard Logging** - Global key listening, grouped by active window, 20-second time clustering
- **Mouse Screenshots** - Single click, double click, drag detection with WebP compression
- **Window Tracking** - Auto-detect active window, blue border annotation on screenshots
- **Microphone Capture** - Records when external apps use the mic; identifies the process via macOS AudioProcess API
- **AI Analysis** - Local Ollama or remote APIs (OpenAI, Anthropic Claude)
- **Audio Transcription** - Whisper-based speech-to-text for recorded audio
- **Report Generation** - Automated daily Markdown reports from captured data
- **Privacy First** - All data processed and stored locally by default

## Install

**Option 1: pip install** (recommended)

```bash
pip install opencapture
```

**Option 2: Clone and develop**

```bash
git clone https://github.com/daibor/opencapture.git
cd opencapture
pip install -e ".[dev]"
```

**Option 3: Download .app** (macOS)

Download from [GitHub Releases](https://github.com/daibor/opencapture/releases).

## Usage

### Capture Mode

```bash
# Start capture (foreground)
opencapture

# Specify storage directory
opencapture -d ~/my-captures

# Or run directly with Python (from cloned repo)
python run.py
```

Press `Ctrl+C` to stop.

### Service Management (macOS)

```bash
opencapture start                      # Start as background service
opencapture stop                       # Stop service
opencapture restart                    # Restart service
opencapture status                     # Show running state and today's stats
opencapture log                        # Show recent service logs
opencapture log -f                     # Follow logs in real-time
```

### Analysis Mode

```bash
# Analyze today's data
opencapture --analyze today

# Analyze specific date
opencapture --analyze 2026-02-01
opencapture --analyze yesterday

# Analyze single image
opencapture --image path/to/screenshot.webp

# Transcribe single audio file
opencapture --audio path/to/mic.wav

# Use remote API
export OPENAI_API_KEY=sk-xxx
opencapture --provider openai --analyze today

# Skip report generation
opencapture --analyze today --no-reports

# Check LLM service health
opencapture --health-check

# List available dates
opencapture --list-dates

# Show help
opencapture --help
```

## System Requirements

- **macOS** 10.15+ (capture + analysis)
- **Linux / Windows** (analysis only)
- Python 3.11+
- 8GB+ RAM (for local AI analysis)
- 10GB+ disk space (for local model storage)

### macOS Permissions

First run requires authorization in **System Settings > Privacy & Security**:

| Permission | Purpose |
|---|---|
| **Accessibility** | Keyboard and mouse event listening |
| **Screen Recording** | Screen capture |
| **Microphone** | Audio recording (if enabled) |

## Data Storage

Default location: `~/opencapture/`

```
~/opencapture/
├── 2026-02-01/
│   ├── 2026-02-01.log                              # Unified log
│   ├── click_103045_123_left_x800_y600.webp        # Click screenshot
│   ├── dblclick_103046_456_left_x800_y600.webp     # Double-click screenshot
│   ├── drag_103050_789_left_x100_y200_to_x500_y400.webp  # Drag screenshot
│   └── mic_103100_000_zoom_dur30.wav               # Mic recording
├── reports/
│   ├── 2026-02-01.md                               # Daily report
│   └── 2026-02-01_images.md                        # Image analysis
└── 2026-02-02/
    └── ...
```

### Log Format

Keyboard input and mouse screenshots are recorded in a unified log file. Different windows are separated by triple newlines:

```
[2026-02-01 10:23:40] Visual Studio Code | index.ts - my-project (com.microsoft.VSCode)
[10:23:45] hello world↩
[10:23:50] ⌘s
[10:23:51] 📷 click (800,600) click_102351_123_left_x800_y600.webp


[2026-02-01 10:25:32] Terminal | zsh (com.apple.Terminal)
[10:25:35] npm run dev↩
[10:26:00] ⌃c
```

### Key Symbols

| Key | Symbol |
|---|---|
| Command | ⌘ |
| Control | ⌃ |
| Option | ⌥ |
| Shift | ⇧ |
| Enter | ↩ |
| Tab | ⇥ |
| Backspace | ⌫ |
| Escape | ⎋ |
| Arrow Keys | ↑↓←→ |

## Configuration

Edit `~/.opencapture/config.yaml` to customize:

```bash
vim ~/.opencapture/config.yaml
```

Key settings:

| Setting | Description |
|---|---|
| `llm.default_provider` | LLM provider (`ollama` / `openai` / `anthropic`) |
| `llm.*.model` | Model selection per provider |
| `capture.output_dir` | Storage directory |
| `capture.mic_enabled` | Enable microphone capture |
| `privacy.allow_online` | Allow remote API providers |
| `prompts.*` | Custom analysis prompts |

Environment variables:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Enable OpenAI provider |
| `ANTHROPIC_API_KEY` | Enable Anthropic Claude provider |
| `OLLAMA_API_URL` | Custom Ollama API endpoint |
| `OLLAMA_MODEL` | Ollama model selection |
| `OPENCAPTURE_ALLOW_ONLINE` | Allow remote providers |

## Uninstall

```bash
pip uninstall opencapture
```

To also remove captured data: `rm -rf ~/opencapture`
To remove config: `rm -rf ~/.opencapture`

## Privacy Warning

This tool records all keyboard input (including passwords) and screen content. Please:

- Ensure storage directory access is secured
- Regularly clean up historical data
- Use for personal purposes only
- Remote providers require explicit `privacy.allow_online: true` in config

## License

[MIT](LICENSE)
