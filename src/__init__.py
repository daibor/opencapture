"""
OpenCapture - 键鼠行为记录与 AI 分析

模块:
- auto_capture: 键盘和鼠标事件捕获
- config: 配置管理
- llm_client: LLM 客户端（支持 Ollama/OpenAI/Anthropic）
- report_generator: Markdown 报告生成
- analyzer: 综合分析器
"""

__version__ = "0.2.0"
__author__ = "OpenCapture"

from .auto_capture import AutoCapture
from .config import Config, get_config, init_config

__all__ = ["AutoCapture", "Config", "get_config", "init_config"]
