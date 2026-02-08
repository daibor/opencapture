"""Tests for opencapture/llm_client.py"""

import pytest
from pathlib import Path

from opencapture.llm_client import (
    AnalysisResult,
    BaseLLMClient,
    OpenAIClient,
    AnthropicClient,
    OllamaClient,
    LLMRouter,
)


# ---------------------------------------------------------------------------
# AnalysisResult
# ---------------------------------------------------------------------------

class TestAnalysisResult:
    def test_to_dict_fields(self):
        r = AnalysisResult(
            success=True,
            content="hello",
            model="gpt-4o",
            provider="openai",
            inference_time=1.5,
            tokens_used=100,
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["content"] == "hello"
        assert d["model"] == "gpt-4o"
        assert d["provider"] == "openai"
        assert d["inference_time"] == 1.5
        assert d["tokens_used"] == 100
        # error should be present but empty
        assert d["error"] == ""

    def test_defaults(self):
        r = AnalysisResult(success=False)
        assert r.content == ""
        assert r.error == ""
        assert r.model == ""
        assert r.provider == ""
        assert r.inference_time == 0.0
        assert r.tokens_used == 0
        assert r.metadata == {}


# ---------------------------------------------------------------------------
# BaseLLMClient._get_image_media_type
# ---------------------------------------------------------------------------

class TestGetImageMediaType:
    @pytest.fixture()
    def client(self):
        # OllamaClient is the simplest concrete subclass
        return OllamaClient()

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("photo.jpg", "image/jpeg"),
            ("photo.jpeg", "image/jpeg"),
            ("photo.png", "image/png"),
            ("photo.webp", "image/webp"),
            ("photo.gif", "image/gif"),
            ("photo.bmp", "image/png"),  # unknown defaults to png
        ],
    )
    def test_known_extensions(self, client, path, expected):
        assert client._get_image_media_type(path) == expected


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------

class TestHeaders:
    def test_openai_headers(self):
        c = OpenAIClient(api_key="sk-test-123")
        h = c._get_headers()
        assert h["Authorization"] == "Bearer sk-test-123"
        assert h["Content-Type"] == "application/json"

    def test_anthropic_headers(self):
        c = AnthropicClient(api_key="sk-ant-test")
        h = c._get_headers()
        assert h["x-api-key"] == "sk-ant-test"
        assert h["anthropic-version"] == "2023-06-01"


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------

class TestLLMRouter:
    def _minimal_config(self, **overrides):
        """Build a minimal LLM config dict."""
        cfg = {
            "default_provider": "ollama",
            "ollama": {"enabled": True, "api_url": "http://localhost:11434", "model": "test"},
            "openai": {"enabled": False},
            "anthropic": {"enabled": False},
            "custom": {"enabled": False},
        }
        cfg.update(overrides)
        return cfg

    def test_get_client_default(self):
        router = LLMRouter(self._minimal_config())
        client = router.get_client()
        assert isinstance(client, OllamaClient)

    def test_get_client_unknown_returns_none(self):
        router = LLMRouter(self._minimal_config())
        assert router.get_client("nonexistent") is None

    def test_list_providers(self):
        router = LLMRouter(self._minimal_config())
        providers = router.list_providers()
        assert "ollama" in providers

    def test_remote_blocked_when_offline(self):
        cfg = self._minimal_config()
        cfg["openai"] = {
            "enabled": True,
            "api_key": "sk-test",
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o",
        }
        router = LLMRouter(cfg, allow_online=False)
        # OpenAI should NOT be initialized
        assert "openai" not in router.clients

    def test_remote_allowed_when_online(self):
        cfg = self._minimal_config()
        cfg["openai"] = {
            "enabled": True,
            "api_key": "sk-test",
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o",
        }
        router = LLMRouter(cfg, allow_online=True)
        assert "openai" in router.clients
        assert isinstance(router.clients["openai"], OpenAIClient)
