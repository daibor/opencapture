# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenCapture is a macOS/Linux tool that records keyboard and mouse activity, captures screenshots, and uses AI (local Ollama or remote APIs) to analyze user behavior. All data is stored locally.

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run capture mode
python run.py                          # Start recording

# Run analysis mode
python run.py --analyze today          # Analyze today's data
python run.py --analyze 2026-02-01     # Analyze specific date
python run.py --image path/to/img.webp # Analyze single image
python run.py --provider openai --analyze today  # Use specific LLM

# Using remote APIs
export OPENAI_API_KEY=sk-xxx
export ANTHROPIC_API_KEY=sk-ant-xxx

# Health check
python run.py --health-check

# List available dates
python run.py --list-dates
```

## Architecture

```
KeyLogger + MouseCapture + WindowTracker
              ↓
         UnifiedLogger
              ↓
    .log files + .webp screenshots
              ↓
         LLM Analyzer (LLMRouter)
         ↙          ↘
    Ollama      Remote APIs
    (local)   (OpenAI/Anthropic)
              ↓
      Markdown Reports
```

**Key modules:**

- `src/auto_capture.py` - Core capture: `KeyLogger`, `MouseCapture`, `WindowTracker`, `AutoCapture`
- `src/llm_client.py` - LLM abstraction: `BaseLLMClient`, `OllamaClient`, `OpenAIClient`, `AnthropicClient`, `LLMRouter`
- `src/analyzer.py` - Orchestrates LLM analysis with `Analyzer` class
- `src/report_generator.py` - Markdown report generation: `ReportGenerator`, `ReportAggregator`
- `src/config.py` - Configuration management with environment variable support
- `run.py` - CLI entry point for both capture and analysis modes

## Configuration

Config priority: Environment variables > `config/config.yaml` > defaults

Key environment variables:
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` - Enable remote LLM providers
- `OLLAMA_API_URL`, `OLLAMA_MODEL` - Local Ollama settings

Copy `config/example.yaml` to `config/config.yaml` for customization. Prompts for image analysis (click/dblclick/drag) and keyboard log analysis are separately configurable.

## Data Format

Screenshots: `{action}_{HHmmss}_{ms}_{button}_x{X}_y{Y}.webp`
- Actions: `click_`, `dblclick_`, `drag_`
- Drag includes: `_to_x{X2}_y{Y2}`

Logs: `~/auto-capture/YYYY-MM-DD/YYYY-MM-DD.log` with window blocks separated by triple newlines.

Reports: `~/auto-capture/reports/YYYY-MM-DD.md` and `YYYY-MM-DD_images.md`

## macOS Requirements

Requires Accessibility and Screen Recording permissions in System Settings > Privacy & Security.
