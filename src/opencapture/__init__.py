"""
OpenCapture - Keyboard/mouse activity recording and AI analysis

Modules:
- auto_capture: Keyboard and mouse event capture
- config: Configuration management
- llm_client: LLM clients (Ollama/OpenAI/Anthropic)
- report_generator: Markdown report generation
- analyzer: Unified analyzer
"""

__version__ = "0.0.0"
__author__ = "OpenCapture"

from .config import Config, get_config, init_config

__all__ = ["Config", "get_config", "init_config"]
