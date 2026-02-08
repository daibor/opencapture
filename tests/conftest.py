"""Shared fixtures for OpenCapture tests."""

import pytest
from pathlib import Path


# Environment variables that could leak real API keys or alter config loading
_SENSITIVE_ENV_VARS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "CUSTOM_API_KEY",
    "OPENCAPTURE_OUTPUT_DIR",
    "OPENCAPTURE_LLM_PROVIDER",
    "OPENCAPTURE_ALLOW_ONLINE",
    "OLLAMA_API_URL",
    "OLLAMA_MODEL",
    "OPENAI_API_BASE",
    "OPENAI_MODEL",
    "ANTHROPIC_MODEL",
    "LOG_LEVEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Strip API key / config env vars so tests never leak real credentials."""
    for var in _SENSITIVE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def sample_config_yaml(tmp_path):
    """Write a minimal YAML config file and return its path."""
    config_file = tmp_path / ".opencapture" / "config.yaml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        "capture:\n"
        "  output_dir: /tmp/oc-test\n"
        "llm:\n"
        "  default_provider: ollama\n"
    )
    return config_file
