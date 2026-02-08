#!/usr/bin/env python3
"""
Configuration Management Module
Supports multiple LLM providers and flexible configuration options
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List


class Config:
    """Configuration manager"""

    # Default configuration
    DEFAULT_CONFIG = {
        # Basic settings
        "capture": {
            "output_dir": "~/opencapture",
            "image_format": "webp",
            "image_quality": 80,
            "throttle_ms": 100,
            "drag_threshold": 10,
            "double_click_interval": 400,
            "double_click_distance": 5,
            "window_border_color": [0, 120, 255],
            "window_border_width": 3,
            "cluster_interval": 20,
            "mic_enabled": False,
            "mic_sample_rate": 16000,
            "mic_channels": 1,
            "mic_start_debounce_ms": 500,
            "mic_stop_debounce_ms": 2000,
        },

        # LLM configuration
        "llm": {
            "default_provider": "ollama",

            "ollama": {
                "enabled": True,
                "api_url": "http://localhost:11434",
                "model": "qwen2-vl:7b",
                "text_model": None,
                "timeout": 120,
                "max_retries": 3,
                "num_ctx": 4096,
            },

            "openai": {
                "enabled": False,
                "api_key": "${OPENAI_API_KEY}",
                "api_base": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "text_model": "gpt-4o-mini",
                "timeout": 60,
                "max_retries": 3,
                "max_tokens": 4096,
            },

            "anthropic": {
                "enabled": False,
                "api_key": "${ANTHROPIC_API_KEY}",
                "api_base": "https://api.anthropic.com",
                "model": "claude-sonnet-4-20250514",
                "text_model": None,
                "timeout": 60,
                "max_retries": 3,
                "max_tokens": 4096,
            },

            "custom": {
                "enabled": False,
                "api_key": "${CUSTOM_API_KEY}",
                "api_base": "",
                "model": "",
                "text_model": None,
                "timeout": 60,
                "max_retries": 3,
                "max_tokens": 4096,
            },
        },

        # Prompt configuration
        "prompts": {
            "image": {
                "system": "You are a professional screen behavior analyst. Analyze user screenshots to understand what the user is doing.",
                "click": "Analyze this screenshot. The user clicked at coordinates ({x}, {y}). Describe: 1) What element was clicked 2) The purpose of this action 3) Current context.",
                "dblclick": "Analyze this screenshot. The user double-clicked at coordinates ({x}, {y}). Describe: 1) What was double-clicked 2) Expected result 3) Current workspace.",
                "drag": "Analyze this screenshot. The user dragged from ({x1}, {y1}) to ({x2}, {y2}). Describe: 1) What was dragged 2) Purpose of the drag 3) Context.",
                "default": "Analyze this screenshot. Describe the main content, active application, and possible user task.",
            },
            "keyboard": {
                "system": "You are a professional user behavior analyst. Analyze keyboard input to understand the user's work.",
                "analyze": "Analyze the following keyboard input in {window}:\n\n```\n{content}\n```\n\nDescribe: 1) Current task 2) Input type (code, document, command, chat) 3) Possible goal.",
            },
            "daily_summary": "Based on the following daily activity records, generate a brief report:\n\n{activities}\n\nInclude: main work, most used apps, notable activities.",
        },

        # ASR (Automatic Speech Recognition) configuration
        "asr": {
            "enabled": False,
            "api_url": "https://api.openai.com/v1",
            "api_key": "${OPENAI_API_KEY}",
            "model": "whisper-1",
            "language": None,  # None = auto-detect
            "timeout": 120,
        },

        # Batch analysis settings
        "scheduler": {
            "batch_size": 10,
            "delay_between_batches": 2,
        },

        # Report configuration
        "reports": {
            "output_dir": "reports",
            "format": "markdown",
            "include_images": True,
            "daily_summary": True,
            "image_analysis": True,
        },

        # Privacy configuration
        "privacy": {
            "allow_online": False,  # Must be explicitly enabled to use remote LLM providers
        },

        # Logging configuration
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(levelname)s - %(message)s",
            "file": None,
        },
    }

    # Environment variable mapping
    ENV_MAPPING = {
        "OPENCAPTURE_OUTPUT_DIR": "capture.output_dir",
        "OPENCAPTURE_LLM_PROVIDER": "llm.default_provider",
        "OLLAMA_API_URL": "llm.ollama.api_url",
        "OLLAMA_MODEL": "llm.ollama.model",
        "OPENAI_API_KEY": "llm.openai.api_key",
        "OPENAI_API_BASE": "llm.openai.api_base",
        "OPENAI_MODEL": "llm.openai.model",
        "ANTHROPIC_API_KEY": "llm.anthropic.api_key",
        "ANTHROPIC_MODEL": "llm.anthropic.model",
        "OPENCAPTURE_ALLOW_ONLINE": "privacy.allow_online",
        "LOG_LEVEL": "logging.level",
    }

    REMOTE_PROVIDERS = {"openai", "anthropic", "custom"}

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration

        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = self._deep_copy(self.DEFAULT_CONFIG)

        # Try auto-loading config file
        if config_path:
            self.load_from_file(config_path)
        else:
            self._auto_load_config()

        # Load environment variables
        self.load_from_env()

        # Expand paths and variables
        self._expand_all()

    def _deep_copy(self, obj: Any) -> Any:
        """Deep copy an object"""
        if isinstance(obj, dict):
            return {k: self._deep_copy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._deep_copy(item) for item in obj]
        return obj

    def _auto_load_config(self):
        """Auto-discover and load configuration file"""
        config_path = Path.home() / ".opencapture" / "config.yaml"
        if config_path.exists():
            self.load_from_file(str(config_path))

    def load_from_file(self, config_path: str):
        """Load configuration from file"""
        config_path = Path(config_path)
        if not config_path.exists():
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                if config_path.suffix in [".yaml", ".yml"]:
                    user_config = yaml.safe_load(f) or {}
                elif config_path.suffix == ".json":
                    user_config = json.load(f)
                else:
                    return

            self.config = self._deep_merge(self.config, user_config)
            self.config_path = str(config_path)
            print(f"Loaded config: {config_path}")

        except Exception as e:
            print(f"Failed to load config: {e}")

    def load_from_env(self):
        """Load configuration from environment variables"""
        for env_name, config_path in self.ENV_MAPPING.items():
            value = os.environ.get(env_name)
            if value:
                self.set(config_path, value)

        # Auto-enable providers if API key is set
        if os.environ.get("OPENAI_API_KEY"):
            self.set("llm.openai.enabled", True)
        if os.environ.get("ANTHROPIC_API_KEY"):
            self.set("llm.anthropic.enabled", True)

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = self._deep_copy(base)

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = self._deep_copy(value)

        return result

    def _expand_all(self):
        """Expand all paths and environment variables"""
        output_dir = self.get("capture.output_dir", "~/opencapture")
        self.set("capture.output_dir", str(Path(output_dir).expanduser()))

    def _resolve_env_var(self, value: Any) -> Any:
        """Resolve environment variable reference"""
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_name = value[2:-1]
            return os.environ.get(env_name, value)
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value

        Args:
            key: Configuration key (dot-separated)
            default: Default value
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return self._resolve_env_var(value)

    def set(self, key: str, value: Any):
        """
        Set configuration value

        Args:
            key: Configuration key (dot-separated)
            value: Value to set
        """
        keys = key.split(".")
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration"""
        return self._deep_copy(self.config.get("llm", {}))

    def get_prompts(self) -> Dict[str, Any]:
        """Get prompt configuration"""
        return self._deep_copy(self.config.get("prompts", {}))

    def get_capture_config(self) -> Dict[str, Any]:
        """Get capture configuration"""
        return self._deep_copy(self.config.get("capture", {}))

    def get_reports_config(self) -> Dict[str, Any]:
        """Get reports configuration"""
        return self._deep_copy(self.config.get("reports", {}))

    def get_default_provider(self) -> str:
        """Get default LLM provider"""
        return self.get("llm.default_provider", "ollama")

    def is_provider_enabled(self, provider: str) -> bool:
        """Check if provider is enabled"""
        return self.get(f"llm.{provider}.enabled", False)

    def get_enabled_providers(self) -> List[str]:
        """Get list of enabled providers"""
        providers = ["ollama", "openai", "anthropic", "custom"]
        return [p for p in providers if self.is_provider_enabled(p)]

    def is_remote_provider(self, provider: str) -> bool:
        """Check if provider sends data to remote servers"""
        return provider in self.REMOTE_PROVIDERS

    def is_online_allowed(self) -> bool:
        """Check if remote/online LLM providers are allowed"""
        value = self.get("privacy.allow_online", False)
        # Handle string values from env vars
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    def get_image_prompt(self, action: str, **kwargs) -> str:
        """
        Get image analysis prompt

        Args:
            action: Action type (click, dblclick, drag, default)
            **kwargs: Format parameters (x, y, x1, y1, x2, y2)
        """
        prompts = self.get("prompts.image", {})
        prompt_template = prompts.get(action) or prompts.get("default", "")
        return prompt_template.format(**kwargs) if kwargs else prompt_template

    def get_keyboard_prompt(self, **kwargs) -> str:
        """
        Get keyboard log analysis prompt

        Args:
            **kwargs: Format parameters (window, content)
        """
        prompts = self.get("prompts.keyboard", {})
        prompt_template = prompts.get("analyze", "")
        return prompt_template.format(**kwargs) if kwargs else prompt_template

    def get_system_prompt(self, prompt_type: str = "image") -> str:
        """Get system prompt"""
        return self.get(f"prompts.{prompt_type}.system", "")

    def get_output_dir(self) -> Path:
        """Get output directory"""
        return Path(self.get("capture.output_dir", "~/opencapture")).expanduser()

    def get_reports_dir(self) -> Path:
        """Get reports directory"""
        output_dir = self.get_output_dir()
        reports_subdir = self.get("reports.output_dir", "reports")
        return output_dir / reports_subdir

    def to_dict(self) -> Dict:
        """Get complete configuration dictionary"""
        return self._deep_copy(self.config)

    def save(self, path: Optional[str] = None):
        """Save configuration to file"""
        save_path = Path(path or self.config_path)
        if not save_path:
            print("No save path specified")
            return

        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                if save_path.suffix in [".yaml", ".yml"]:
                    yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
                else:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
            print(f"Config saved: {save_path}")
        except Exception as e:
            print(f"Failed to save config: {e}")


# Global configuration instance
_global_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance"""
    global _global_config
    if _global_config is None:
        _global_config = Config()
    return _global_config


def init_config(config_path: Optional[str] = None) -> Config:
    """Initialize global configuration"""
    global _global_config
    _global_config = Config(config_path)
    return _global_config


def reset_config():
    """Reset global configuration"""
    global _global_config
    _global_config = None


if __name__ == "__main__":
    config = Config()
    print("Default configuration:")
    print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))

    print(f"\nDefault provider: {config.get_default_provider()}")
    print(f"Enabled providers: {config.get_enabled_providers()}")
    print(f"Output directory: {config.get_output_dir()}")

    print(f"\nClick prompt: {config.get_image_prompt('click', x=100, y=200)}")
