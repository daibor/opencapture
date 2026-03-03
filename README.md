# OpenCapture

**Context capture for proactive AI agents. Keyboard, mouse, screenshots, audio -- collected naturally, stored locally.**

[![PyPI](https://img.shields.io/pypi/v/opencapture)](https://pypi.org/project/opencapture/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

[Chinese / 中文](README_zh.md)

---

## Why OpenCapture?

**No context, no proactive agent.**

Proactive AI agents need to understand what you are doing before they can help. Without rich, continuous context about your work, an agent can only react to explicit commands -- it can never anticipate your needs.

OpenCapture solves this by collecting context naturally and non-intrusively in the background: every keystroke, mouse action, screenshot, and microphone event is recorded as you work. You do not need to manually log anything. The result is a detailed activity stream that proactive agents can reason over.

### Design Principles

- **Non-intrusive capture** -- runs silently in the background; no workflow disruption
- **Local-first** -- all data stored and processed on your machine by default
- **Privacy by design** -- remote APIs require explicit opt-in; no data leaves your machine unless you choose
- **AI-powered understanding** -- not just raw logs, but structured analysis via local or cloud LLMs

## Features

- **Keyboard Logging** -- global key listening, grouped by active window, 20-second time clustering
- **Mouse Screenshots** -- single click, double click, drag detection with WebP compression
- **Window Tracking** -- auto-detect active window with blue border annotation on screenshots
- **Microphone Capture** -- records when external apps use the mic; identifies the process via macOS AudioProcess API
- **AI Analysis** -- local Ollama or remote APIs (OpenAI, Anthropic Claude)
- **Audio Transcription** -- Whisper-based speech-to-text for recorded audio
- **Report Generation** -- automated daily Markdown reports from captured data
- **macOS Menu Bar App** -- system tray GUI with real-time log window and one-click analysis
- **Background Service** -- launchd integration for always-on capture

## Quick Start

### Install

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

### Run

```bash
# Start capture (foreground)
opencapture

# Launch macOS menu bar GUI
opencapture gui

# Start as background service (macOS)
opencapture start

# Analyze today's captured data
opencapture --analyze today

# Check service status
opencapture status
```

### GUI

The menu bar app provides a visual interface for controlling capture and triggering analysis:

```bash
opencapture gui          # Launch from CLI
opencapture-gui          # Standalone entry point
```

### Service Management (macOS)

```bash
opencapture start        # Start as background service
opencapture stop         # Stop service
opencapture restart      # Restart service
opencapture status       # Show running state and today's stats
opencapture log [-f]     # Show/follow service logs
```

### Analysis

```bash
# Analyze today's data
opencapture --analyze today

# Analyze specific date
opencapture --analyze 2026-02-01
opencapture --analyze yesterday

# Analyze single image or audio file
opencapture --image path/to/screenshot.webp
opencapture --audio path/to/mic.wav

# Use a specific remote provider
export OPENAI_API_KEY=sk-xxx
opencapture --provider openai --analyze today

# Skip report generation
opencapture --analyze today --no-reports

# Utilities
opencapture --health-check     # Check LLM service health
opencapture --list-dates       # List available capture dates
opencapture --help             # Show all options
```

## Security & Privacy

OpenCapture is designed with a strict privacy model:

| Principle | Detail |
|---|---|
| **Local by default** | All captured data stays on your machine in `~/opencapture/` |
| **Explicit opt-in for remote** | Remote LLM providers (OpenAI, Anthropic) require `privacy.allow_online: true` in config |
| **Confirmation prompt** | Before sending data to any remote API, a confirmation prompt is shown |
| **No telemetry** | OpenCapture sends zero telemetry or analytics data |
| **You own your data** | All files are plain text logs, WebP images, WAV audio, and Markdown reports |

**Privacy warning:** This tool records all keyboard input (including passwords) and screen content. Ensure your storage directory has appropriate access controls. Use for personal purposes only.

## Architecture

Three-layer design separating core components, engines, and frontends:

```mermaid
graph TD
    subgraph "Layer 2: Frontends"
        CLI["CLI<br/>cli.py"]
        GUI["GUI Menu Bar<br/>app.py"]
        SVC["Service<br/>launchd"]
    end

    subgraph "Layer 1: Engines — engine.py"
        CE["CaptureEngine<br/>lifecycle + event dispatch"]
        AE["AnalysisEngine<br/>async analysis + progress"]
    end

    subgraph "Layer 0: Core Components"
        KL["KeyLogger"]
        MC["MouseCapture"]
        WT["WindowTracker"]
        MIC["MicrophoneCapture"]
        KL & MC & WT & MIC --> LOG["KeyLogger<br/>unified log writer"]
        MIC --> WAV[".wav recordings"]
        LOG --> FILES[".log files + .webp screenshots"]
        FILES --> ANA["Analyzer"]
        WAV --> ANA
        ANA --> LLM["LLMRouter"]
        ANA --> ASR["ASRClient"]
        LLM --> Ollama["Ollama<br/>local"]
        LLM --> Remote["Remote APIs"]
        ASR --> Whisper["Whisper API"]
        ANA --> RPT["ReportGenerator + ReportAggregator"]
        RPT --> MD["Markdown Reports"]
    end

    CLI --> CE
    GUI --> CE
    GUI --> AE
    SVC --> CLI
    CE --> KL
    AE --> ANA
```

**Key modules:**

| Module | Purpose |
|---|---|
| `auto_capture.py` | Core capture: KeyLogger, MouseCapture, WindowTracker |
| `mic_capture.py` | Microphone monitoring via Core Audio + sounddevice |
| `engine.py` | CaptureEngine (lifecycle) + AnalysisEngine (async analysis) |
| `app.py` | macOS menu bar GUI (PyObjC) |
| `llm_client.py` | LLM abstraction: Ollama, OpenAI, Anthropic, custom providers |
| `analyzer.py` | Orchestrates LLM analysis and audio transcription |
| `report_generator.py` | Markdown report generation and aggregation |
| `config.py` | Configuration management with environment variable support |
| `cli.py` | Unified CLI: capture, analysis, service management, GUI launch |

## OpenClaw Ecosystem

OpenCapture is the **context capture layer** for the [OpenClaw](https://github.com/nicekate) proactive agent ecosystem.

```
User Activity  -->  OpenCapture  -->  Context Stream  -->  Proactive Agent
```

The proactive agent philosophy is simple: an AI that can anticipate your needs must first understand what you are doing. OpenCapture provides that understanding by building a continuous, structured record of your work -- the raw material that proactive agents consume to make intelligent suggestions, automate repetitive tasks, and surface relevant information at the right moment.

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
│   ├── 2026-02-01.log                              # Unified activity log
│   ├── click_103045_123_left_x800_y600.webp        # Click screenshot
│   ├── dblclick_103046_456_left_x800_y600.webp     # Double-click screenshot
│   ├── drag_103050_789_left_x100_y200_to_x500_y400.webp  # Drag screenshot
│   └── mic_103100_000_zoom_dur30.wav               # Mic recording
├── reports/
│   ├── 2026-02-01.md                               # Daily report
│   └── 2026-02-01_images.md                        # Image analysis report
└── 2026-02-02/
    └── ...
```

## Configuration

Edit `~/.opencapture/config.yaml` to customize behavior:

```bash
vim ~/.opencapture/config.yaml
```

### Key Settings

| Setting | Description |
|---|---|
| `llm.default_provider` | LLM provider: `ollama` / `openai` / `anthropic` / `custom` |
| `llm.*.model` | Model selection per provider |
| `capture.output_dir` | Data storage directory |
| `capture.mic_enabled` | Enable microphone capture |
| `privacy.allow_online` | Allow remote API providers |
| `prompts.*` | Custom analysis prompts |

### Environment Variables

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Enable OpenAI provider |
| `ANTHROPIC_API_KEY` | Enable Anthropic Claude provider |
| `OLLAMA_API_URL` | Custom Ollama API endpoint |
| `OLLAMA_MODEL` | Ollama model selection |
| `OPENCAPTURE_ALLOW_ONLINE` | Allow remote providers |

Config priority: Environment variables > `~/.opencapture/config.yaml` > built-in defaults.

## Uninstall

```bash
pip uninstall opencapture
```

To remove captured data: `rm -rf ~/opencapture`
To remove config: `rm -rf ~/.opencapture`

## Contributing

```bash
git clone https://github.com/daibor/opencapture.git
cd opencapture
pip install -e ".[dev]"
pytest tests/ -v
```

See [architecture docs](docs/specs/architecture.md) for detailed design information.

## License

[MIT](LICENSE)
