# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenCapture is a macOS/Linux tool that records keyboard and mouse activity, captures screenshots, optionally records microphone audio, and uses AI (local Ollama or remote APIs) to analyze user behavior. All data is stored locally.

## Installation & Commands

```bash
# Setup (development)
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Run capture mode (foreground)
python run.py                          # Start recording (dev entry point)
opencapture                            # Start recording (installed CLI)

# Run analysis mode
opencapture --analyze today            # Analyze today's data
opencapture --analyze 2026-02-01       # Analyze specific date
opencapture --image path/to/img.webp   # Analyze single image
opencapture --audio path/to/mic.wav    # Transcribe single audio
opencapture --provider openai --analyze today  # Use specific LLM

# Using remote APIs (requires privacy.allow_online: true in config)
export OPENAI_API_KEY=sk-xxx
export ANTHROPIC_API_KEY=sk-ant-xxx

# Utilities
opencapture --health-check             # Check LLM service status
opencapture --list-dates               # List available dates

# Service management (macOS launchd)
opencapture start                      # Start as background service
opencapture stop                       # Stop service
opencapture restart                    # Restart service
opencapture status                     # Show running state and today's stats
opencapture log [-f]                   # Show/follow service logs

# Three install methods:
# 1. Clone repo:    python run.py
# 2. pip install:   pip install opencapture && opencapture
# 3. .app bundle:   Download from GitHub Releases (PyInstaller)
```

## Architecture

```
KeyLogger + MouseCapture + WindowTracker + MicrophoneCapture
              ↓                                ↓
         KeyLogger (unified log writer)   .wav recordings
              ↓
    .log files + .webp screenshots
              ↓
         Analyzer → LLMRouter + ASRClient
                    ↙    ↘        ↘
               Ollama  Remote   Whisper API
              (local)  APIs     (transcription)
                    ↓
         ReportGenerator + ReportAggregator
                    ↓
            Markdown Reports
```

**Key modules:**

- `src/opencapture/auto_capture.py` - Core capture: `KeyLogger`, `MouseCapture`, `WindowTracker`, `AutoCapture`
- `src/opencapture/mic_capture.py` - Microphone monitoring: `MicrophoneCapture` (Core Audio ctypes + sounddevice). Records when external apps use the mic; identifies which process via macOS 14+ AudioProcess API
- `src/opencapture/llm_client.py` - LLM abstraction: `BaseLLMClient`, `OllamaClient`, `OpenAIClient`, `AnthropicClient`, `LLMRouter`, `ASRClient`
- `src/opencapture/analyzer.py` - Orchestrates LLM analysis and audio transcription with `Analyzer` class
- `src/opencapture/report_generator.py` - Markdown report generation: `ReportGenerator`, `ReportAggregator`
- `src/opencapture/config.py` - Configuration management with environment variable support
- `src/opencapture/cli.py` - Unified CLI: capture, analysis, and service management (start/stop/status/log)
- `run.py` - Development entry point (thin wrapper with sys.path hack)
- `packaging/macos.spec` - PyInstaller spec for macOS .app bundle

## Configuration

Config priority: Environment variables > `~/.opencapture/config.yaml` > defaults

Key environment variables:
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` - Enable remote LLM providers (auto-sets `llm.*.enabled: true`)
- `OLLAMA_API_URL`, `OLLAMA_MODEL` - Local Ollama settings
- `OPENCAPTURE_ALLOW_ONLINE` - Allow remote providers (privacy gate)

Example config is bundled at `src/opencapture/config/example.yaml`. Prompts for image analysis (click/dblclick/drag) and keyboard log analysis are separately configurable.

Privacy: Remote providers (openai/anthropic/custom) require `privacy.allow_online: true` in config. The analyzer shows a confirmation prompt before sending data to remote APIs.

## Data Format

Screenshots: `{action}_{HHmmss}_{ms}_{button}_x{X}_y{Y}.webp`
- Actions: `click_`, `dblclick_`, `drag_`
- Drag includes: `_to_x{X2}_y{Y2}`

Audio: `mic_{HHmmss}_{ms}_{app}_dur{N}.wav` (16kHz mono PCM)
- Recorded only when external apps use the microphone
- Short recordings (< `mic_min_duration_ms`) are discarded

Logs: `~/opencapture/YYYY-MM-DD/YYYY-MM-DD.log` with window blocks separated by triple newlines.
- `📷` lines = screenshot events, `⌨️` lines = keyboard input, `🎤` lines = mic events (mic_start/mic_stop/mic_join/mic_leave)

Analysis: Each `.webp` and `.wav` gets a companion `.txt` file with the LLM/ASR result.

Reports: `~/opencapture/reports/YYYY-MM-DD.md` and `YYYY-MM-DD_images.md`

## macOS Requirements

Requires permissions in System Settings > Privacy & Security:
- **Accessibility** - for keyboard/mouse monitoring
- **Screen Recording** - for screenshots
- **Microphone** - for audio recording (if `mic_enabled: true`)

When built with PyInstaller, the `.app` bundle (`OpenCapture.app`) has bundle ID `com.opencapture.agent` so macOS TCC shows "OpenCapture" in permission dialogs.

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
