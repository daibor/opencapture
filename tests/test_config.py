"""Tests for opencapture/config.py"""

import pytest
from pathlib import Path

from opencapture.config import Config, get_config, init_config, reset_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _isolated_config(tmp_path, monkeypatch):
    """Return a Config that won't load the real ~/.opencapture/config.yaml."""
    # Point Path.home() at tmp_path so _auto_load_config finds nothing
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return Config()


# ---------------------------------------------------------------------------
# Default config structure
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_nested_keys_exist(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        assert cfg.get("capture.image_format") == "webp"
        assert cfg.get("capture.image_quality") == 80
        assert cfg.get("llm.default_provider") == "ollama"

    def test_default_provider_is_ollama(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        assert cfg.get_default_provider() == "ollama"

    def test_get_missing_key_returns_default(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        assert cfg.get("nonexistent.key") is None
        assert cfg.get("nonexistent.key", 42) == 42

    def test_output_dir_expanded(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        out = cfg.get("capture.output_dir")
        assert "~" not in out  # should be expanded


# ---------------------------------------------------------------------------
# set() and intermediate key creation
# ---------------------------------------------------------------------------

class TestSet:
    def test_set_creates_intermediate_keys(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        cfg.set("a.b.c", "deep")
        assert cfg.get("a.b.c") == "deep"

    def test_set_overwrites_existing(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        cfg.set("capture.image_format", "png")
        assert cfg.get("capture.image_format") == "png"


# ---------------------------------------------------------------------------
# _deep_merge / _deep_copy
# ---------------------------------------------------------------------------

class TestDeepMergeCopy:
    def test_deep_merge_preserves_non_overridden(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        base = {"a": 1, "b": {"x": 10, "y": 20}}
        override = {"b": {"x": 99}}
        merged = cfg._deep_merge(base, override)
        assert merged["a"] == 1
        assert merged["b"]["x"] == 99
        assert merged["b"]["y"] == 20

    def test_deep_copy_isolation(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        original = {"a": {"b": [1, 2, 3]}}
        copy = cfg._deep_copy(original)
        copy["a"]["b"].append(4)
        assert original["a"]["b"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Load from YAML file
# ---------------------------------------------------------------------------

class TestLoadFromFile:
    def test_load_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text(
            "capture:\n"
            "  image_quality: 50\n"
            "llm:\n"
            "  default_provider: openai\n"
        )
        cfg = Config(config_path=str(yaml_path))
        assert cfg.get("capture.image_quality") == 50
        assert cfg.get_default_provider() == "openai"
        # Non-overridden key preserved
        assert cfg.get("capture.image_format") == "webp"

    def test_load_nonexistent_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        cfg = Config(config_path=str(tmp_path / "nope.yaml"))
        # Should still have defaults
        assert cfg.get_default_provider() == "ollama"


# ---------------------------------------------------------------------------
# Env var loading
# ---------------------------------------------------------------------------

class TestEnvVars:
    def test_env_overrides_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setenv("OPENCAPTURE_LLM_PROVIDER", "openai")
        cfg = Config()
        assert cfg.get_default_provider() == "openai"

    def test_openai_key_enables_provider(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        cfg = Config()
        assert cfg.is_provider_enabled("openai") is True

    def test_anthropic_key_enables_provider(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        cfg = Config()
        assert cfg.is_provider_enabled("anthropic") is True


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

class TestPrompts:
    def test_get_image_prompt_click(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        prompt = cfg.get_image_prompt("click", x=100, y=200)
        assert "100" in prompt
        assert "200" in prompt

    def test_get_keyboard_prompt(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        prompt = cfg.get_keyboard_prompt(window="Terminal", content="ls -la")
        assert "Terminal" in prompt
        assert "ls -la" in prompt


# ---------------------------------------------------------------------------
# Privacy / online helpers
# ---------------------------------------------------------------------------

class TestPrivacy:
    def test_is_remote_provider(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        assert cfg.is_remote_provider("openai") is True
        assert cfg.is_remote_provider("anthropic") is True
        assert cfg.is_remote_provider("custom") is True
        assert cfg.is_remote_provider("ollama") is False

    def test_is_online_allowed_default_false(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        assert cfg.is_online_allowed() is False

    def test_is_online_allowed_string_true(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        cfg.set("privacy.allow_online", "true")
        assert cfg.is_online_allowed() is True

    def test_is_online_allowed_string_1(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        cfg.set("privacy.allow_online", "1")
        assert cfg.is_online_allowed() is True

    def test_is_online_allowed_string_false(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        cfg.set("privacy.allow_online", "false")
        assert cfg.is_online_allowed() is False


# ---------------------------------------------------------------------------
# Enabled providers
# ---------------------------------------------------------------------------

class TestEnabledProviders:
    def test_default_only_ollama(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        enabled = cfg.get_enabled_providers()
        assert "ollama" in enabled
        assert "openai" not in enabled

    def test_enable_openai(self, tmp_path, monkeypatch):
        cfg = _isolated_config(tmp_path, monkeypatch)
        cfg.set("llm.openai.enabled", True)
        enabled = cfg.get_enabled_providers()
        assert "openai" in enabled


# ---------------------------------------------------------------------------
# Global singleton lifecycle
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_init_get_reset_cycle(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        reset_config()

        cfg1 = init_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

        reset_config()
        cfg3 = get_config()
        assert cfg3 is not cfg1
