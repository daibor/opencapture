#!/usr/bin/env python3
"""
LLM Client - Unified interface for multiple LLM providers
Supports: Ollama, OpenAI, Anthropic, Custom (OpenAI-compatible)
"""

import asyncio
import aiohttp
import base64
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of LLM analysis"""
    success: bool
    content: str = ""
    raw_response: str = ""
    error: str = ""
    model: str = ""
    provider: str = ""
    inference_time: float = 0.0
    tokens_used: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "error": self.error,
            "model": self.model,
            "provider": self.provider,
            "inference_time": self.inference_time,
            "tokens_used": self.tokens_used,
        }


class BaseLLMClient(ABC):
    """Base class for LLM clients"""

    def __init__(
        self,
        api_url: str,
        model: str,
        timeout: int = 60,
        max_retries: int = 3,
        **kwargs
    ):
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None
        self.provider_name = "base"

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the underlying aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    def _encode_image(self, image_path: str) -> Optional[str]:
        """Encode image to base64"""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            return None

    def _get_image_media_type(self, image_path: str) -> str:
        """Get image MIME type from file extension"""
        ext = Path(image_path).suffix.lower()
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return media_types.get(ext, "image/png")

    @abstractmethod
    async def analyze_image(
        self,
        image_path: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AnalysisResult:
        """Analyze an image with the LLM"""
        pass

    @abstractmethod
    async def analyze_text(
        self,
        text: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AnalysisResult:
        """Analyze text with the LLM"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the LLM service is available"""
        pass


class OllamaClient(BaseLLMClient):
    """Ollama API client for local LLM inference"""

    def __init__(
        self,
        api_url: str = "http://localhost:11434",
        model: str = "qwen2-vl:7b",
        text_model: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
        num_ctx: int = 4096,
        **kwargs
    ):
        super().__init__(api_url, model, timeout, max_retries)
        self.text_model = text_model or model
        self.num_ctx = num_ctx
        self.provider_name = "ollama"

    async def health_check(self) -> bool:
        """Check if Ollama service and model are available"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    if self.model in models:
                        logger.info(f"Ollama service OK, model {self.model} loaded")
                        return True
                    else:
                        logger.warning(
                            f"Model '{self.model}' not found. "
                            f"Run: ollama pull {self.model}"
                        )
                        if models:
                            logger.info(f"Available models: {', '.join(models)}")
                        return False
        except aiohttp.ClientConnectorError:
            logger.error(
                f"Cannot connect to Ollama at {self.api_url}. "
                f"Please ensure Ollama is installed and running: ollama serve"
            )
            return False
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    async def analyze_image(
        self,
        image_path: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs
    ) -> AnalysisResult:
        """Analyze image using Ollama"""
        await self._ensure_session()

        image_base64 = self._encode_image(image_path)
        if not image_base64:
            return AnalysisResult(
                success=False,
                error=f"Cannot read image: {image_path}",
                provider=self.provider_name
            )

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "images": [image_base64],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
            }
        }

        return await self._request(payload)

    async def analyze_text(
        self,
        text: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs
    ) -> AnalysisResult:
        """Analyze text using Ollama"""
        await self._ensure_session()

        full_prompt = prompt.replace("{content}", text)
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{full_prompt}"

        payload = {
            "model": self.text_model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
            }
        }

        return await self._request(payload)

    async def _request(self, payload: Dict) -> AnalysisResult:
        """Send request to Ollama API"""
        import time
        start_time = time.time()
        last_error = ""

        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.api_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result.get("response", "")
                        inference_time = time.time() - start_time

                        return AnalysisResult(
                            success=True,
                            content=response_text.strip(),
                            raw_response=response_text,
                            model=self.model,
                            provider=self.provider_name,
                            inference_time=inference_time,
                        )
                    elif response.status == 404:
                        last_error = (
                            f"Model '{payload.get('model', self.model)}' not found. "
                            f"Run: ollama pull {payload.get('model', self.model)}"
                        )
                        logger.error(last_error)
                        break  # No point retrying
                    else:
                        error_text = await response.text()
                        last_error = f"Ollama API error {response.status}: {error_text}"
                        logger.error(last_error)

            except aiohttp.ClientConnectorError:
                last_error = (
                    f"Cannot connect to Ollama at {self.api_url}. "
                    f"Please ensure Ollama is running: ollama serve"
                )
                logger.error(last_error)
            except asyncio.TimeoutError:
                last_error = f"Request timeout ({self.timeout}s)"
                logger.warning(f"Ollama request timeout (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Ollama request failed: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return AnalysisResult(
            success=False,
            error=last_error or "Max retries exceeded",
            provider=self.provider_name,
            inference_time=time.time() - start_time
        )


class OpenAIClient(BaseLLMClient):
    """OpenAI API client"""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        text_model: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
        max_tokens: int = 4096,
        **kwargs
    ):
        super().__init__(api_base, model, timeout, max_retries)
        self.api_key = self._resolve_env_var(api_key)
        self.text_model = text_model or "gpt-4o-mini"
        self.max_tokens = max_tokens
        self.provider_name = "openai"

    def _resolve_env_var(self, value: str) -> str:
        """Resolve environment variable reference"""
        if value and value.startswith("${") and value.endswith("}"):
            env_name = value[2:-1]
            return os.environ.get(env_name, "")
        return value

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/models",
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    logger.info("OpenAI API connection OK")
                    return True
                else:
                    logger.warning(f"OpenAI API returned {response.status}")
                    return False
        except Exception as e:
            logger.error(f"OpenAI health check failed: {e}")
            return False

    async def analyze_image(
        self,
        image_path: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AnalysisResult:
        """Analyze image using OpenAI API"""
        await self._ensure_session()

        image_base64 = self._encode_image(image_path)
        if not image_base64:
            return AnalysisResult(
                success=False,
                error=f"Cannot read image: {image_path}",
                provider=self.provider_name
            )

        media_type = self._get_image_media_type(image_path)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{image_base64}"
                    }
                }
            ]
        })

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature,
        }

        return await self._request(payload)

    async def analyze_text(
        self,
        text: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AnalysisResult:
        """Analyze text using OpenAI API"""
        await self._ensure_session()

        full_prompt = prompt.replace("{content}", text)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": full_prompt})

        payload = {
            "model": self.text_model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature,
        }

        return await self._request(payload)

    async def _request(self, payload: Dict) -> AnalysisResult:
        """Send request to OpenAI API"""
        import time
        start_time = time.time()

        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.api_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    result = await response.json()

                    if response.status == 200:
                        content = result["choices"][0]["message"]["content"]
                        tokens = result.get("usage", {}).get("total_tokens", 0)

                        return AnalysisResult(
                            success=True,
                            content=content.strip(),
                            raw_response=json.dumps(result),
                            model=payload.get("model", self.model),
                            provider=self.provider_name,
                            inference_time=time.time() - start_time,
                            tokens_used=tokens,
                        )
                    else:
                        error_msg = result.get("error", {}).get("message", str(result))
                        logger.error(f"OpenAI API error: {error_msg}")

            except asyncio.TimeoutError:
                logger.warning(f"OpenAI request timeout (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                logger.error(f"OpenAI request failed: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return AnalysisResult(
            success=False,
            error="Max retries exceeded",
            provider=self.provider_name,
            inference_time=time.time() - start_time
        )


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API client"""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.anthropic.com",
        model: str = "claude-sonnet-4-20250514",
        text_model: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
        max_tokens: int = 4096,
        **kwargs
    ):
        super().__init__(api_base, model, timeout, max_retries)
        self.api_key = self._resolve_env_var(api_key)
        self.text_model = text_model or model
        self.max_tokens = max_tokens
        self.provider_name = "anthropic"

    def _resolve_env_var(self, value: str) -> str:
        """Resolve environment variable reference"""
        if value and value.startswith("${") and value.endswith("}"):
            env_name = value[2:-1]
            return os.environ.get(env_name, "")
        return value

    def _get_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    async def health_check(self) -> bool:
        """Check if Anthropic API key format is valid"""
        if self.api_key and self.api_key.startswith("sk-ant-"):
            logger.info("Anthropic API key format OK")
            return True
        logger.warning("Anthropic API key format invalid")
        return False

    async def analyze_image(
        self,
        image_path: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AnalysisResult:
        """Analyze image using Claude API"""
        await self._ensure_session()

        image_base64 = self._encode_image(image_path)
        if not image_base64:
            return AnalysisResult(
                success=False,
                error=f"Cannot read image: {image_path}",
                provider=self.provider_name
            )

        media_type = self._get_image_media_type(image_path)

        payload = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            }
                        },
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        }

        if system_prompt:
            payload["system"] = system_prompt

        return await self._request(payload)

    async def analyze_text(
        self,
        text: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AnalysisResult:
        """Analyze text using Claude API"""
        await self._ensure_session()

        full_prompt = prompt.replace("{content}", text)

        payload = {
            "model": self.text_model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": [
                {"role": "user", "content": full_prompt}
            ]
        }

        if system_prompt:
            payload["system"] = system_prompt

        return await self._request(payload)

    async def _request(self, payload: Dict) -> AnalysisResult:
        """Send request to Anthropic API"""
        import time
        start_time = time.time()

        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.api_url}/v1/messages",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    result = await response.json()

                    if response.status == 200:
                        content = result["content"][0]["text"]
                        tokens = result.get("usage", {})
                        total_tokens = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)

                        return AnalysisResult(
                            success=True,
                            content=content.strip(),
                            raw_response=json.dumps(result),
                            model=payload.get("model", self.model),
                            provider=self.provider_name,
                            inference_time=time.time() - start_time,
                            tokens_used=total_tokens,
                        )
                    else:
                        error_msg = result.get("error", {}).get("message", str(result))
                        logger.error(f"Anthropic API error: {error_msg}")

            except asyncio.TimeoutError:
                logger.warning(f"Anthropic request timeout (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                logger.error(f"Anthropic request failed: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return AnalysisResult(
            success=False,
            error="Max retries exceeded",
            provider=self.provider_name,
            inference_time=time.time() - start_time
        )


class LLMRouter:
    """LLM Router - Manages multiple LLM clients and routes requests"""

    REMOTE_PROVIDERS = {"openai", "anthropic", "custom"}

    def __init__(self, config: Dict[str, Any], allow_online: bool = False,
                 asr_config: Optional[Dict[str, Any]] = None):
        self.config = config
        self.clients: Dict[str, BaseLLMClient] = {}
        self.allow_online = allow_online
        self.default_provider = config.get("default_provider", "ollama")
        self.asr_client: Optional[ASRClient] = None
        self._init_clients()
        self._init_asr(asr_config)

    def _init_clients(self):
        """Initialize all enabled clients"""
        llm_config = self.config

        # Ollama
        ollama_cfg = llm_config.get("ollama", {})
        if ollama_cfg.get("enabled", True):
            self.clients["ollama"] = OllamaClient(
                api_url=ollama_cfg.get("api_url", "http://localhost:11434"),
                model=ollama_cfg.get("model", "qwen2-vl:7b"),
                text_model=ollama_cfg.get("text_model"),
                timeout=ollama_cfg.get("timeout", 120),
                max_retries=ollama_cfg.get("max_retries", 3),
                num_ctx=ollama_cfg.get("num_ctx", 4096),
            )

        # Remote providers — only initialize if online mode is allowed
        if not self.allow_online:
            return

        # OpenAI
        openai_cfg = llm_config.get("openai", {})
        if openai_cfg.get("enabled", False):
            api_key = openai_cfg.get("api_key", "${OPENAI_API_KEY}")
            self.clients["openai"] = OpenAIClient(
                api_key=api_key,
                api_base=openai_cfg.get("api_base", "https://api.openai.com/v1"),
                model=openai_cfg.get("model", "gpt-4o"),
                text_model=openai_cfg.get("text_model", "gpt-4o-mini"),
                timeout=openai_cfg.get("timeout", 60),
                max_retries=openai_cfg.get("max_retries", 3),
                max_tokens=openai_cfg.get("max_tokens", 4096),
            )

        # Anthropic
        anthropic_cfg = llm_config.get("anthropic", {})
        if anthropic_cfg.get("enabled", False):
            api_key = anthropic_cfg.get("api_key", "${ANTHROPIC_API_KEY}")
            self.clients["anthropic"] = AnthropicClient(
                api_key=api_key,
                api_base=anthropic_cfg.get("api_base", "https://api.anthropic.com"),
                model=anthropic_cfg.get("model", "claude-sonnet-4-20250514"),
                text_model=anthropic_cfg.get("text_model"),
                timeout=anthropic_cfg.get("timeout", 60),
                max_retries=anthropic_cfg.get("max_retries", 3),
                max_tokens=anthropic_cfg.get("max_tokens", 4096),
            )

        # Custom (OpenAI-compatible)
        custom_cfg = llm_config.get("custom", {})
        if custom_cfg.get("enabled", False):
            api_key = custom_cfg.get("api_key", "${CUSTOM_API_KEY}")
            self.clients["custom"] = OpenAIClient(
                api_key=api_key,
                api_base=custom_cfg.get("api_base", ""),
                model=custom_cfg.get("model", ""),
                text_model=custom_cfg.get("text_model"),
                timeout=custom_cfg.get("timeout", 60),
                max_retries=custom_cfg.get("max_retries", 3),
                max_tokens=custom_cfg.get("max_tokens", 4096),
            )
            self.clients["custom"].provider_name = "custom"

    def _init_asr(self, asr_config: Optional[Dict[str, Any]]):
        """Initialize ASR client if configured."""
        if not asr_config or not asr_config.get("enabled", False):
            return
        self.asr_client = ASRClient(
            api_url=asr_config.get("api_url", "https://api.openai.com/v1"),
            api_key=asr_config.get("api_key", ""),
            model=asr_config.get("model", "whisper-1"),
            language=asr_config.get("language"),
            timeout=asr_config.get("timeout", 120),
        )

    def get_client(self, provider: Optional[str] = None) -> Optional[BaseLLMClient]:
        """Get specified or default client"""
        provider = provider or self.default_provider
        return self.clients.get(provider)

    def list_providers(self) -> List[str]:
        """List all available providers"""
        return list(self.clients.keys())

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health status of all clients"""
        results = {}
        for name, client in self.clients.items():
            results[name] = await client.health_check()
        return results

    async def analyze_image(
        self,
        image_path: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs
    ) -> AnalysisResult:
        """Analyze image using specified or default provider"""
        client = self.get_client(provider)
        if not client:
            return AnalysisResult(
                success=False,
                error=f"Provider {provider or self.default_provider} not available"
            )
        return await client.analyze_image(image_path, prompt, system_prompt, **kwargs)

    async def analyze_text(
        self,
        text: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs
    ) -> AnalysisResult:
        """Analyze text using specified or default provider"""
        client = self.get_client(provider)
        if not client:
            return AnalysisResult(
                success=False,
                error=f"Provider {provider or self.default_provider} not available"
            )
        return await client.analyze_text(text, prompt, system_prompt, **kwargs)

    async def transcribe_audio(self, audio_path: str) -> AnalysisResult:
        """Transcribe audio using the configured ASR client."""
        if not self.asr_client:
            return AnalysisResult(
                success=False,
                error="ASR not configured. Enable it in config: asr.enabled: true"
            )
        return await self.asr_client.transcribe(audio_path)

    async def close(self):
        """Close all client sessions"""
        for client in self.clients.values():
            await client.close()
        if self.asr_client:
            await self.asr_client.close()


class ASRClient:
    """OpenAI-compatible ASR client for audio transcription.

    Works with OpenAI Whisper API, faster-whisper-server, or any service
    that implements POST /v1/audio/transcriptions with multipart form data.
    """

    def __init__(
        self,
        api_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "whisper-1",
        language: Optional[str] = None,
        timeout: int = 120,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = self._resolve_env_var(api_key)
        self.model = model
        self.language = language
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None

    def _resolve_env_var(self, value: str) -> str:
        if value and value.startswith("${") and value.endswith("}"):
            env_name = value[2:-1]
            return os.environ.get(env_name, "")
        return value

    async def _ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the underlying aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def transcribe(self, audio_path: str) -> AnalysisResult:
        """Transcribe an audio file to text.

        Posts the audio file as multipart form data to the
        OpenAI-compatible /v1/audio/transcriptions endpoint.
        """
        import time
        start_time = time.time()

        audio_path = Path(audio_path)
        if not audio_path.exists():
            return AnalysisResult(
                success=False,
                error=f"Audio file not found: {audio_path}",
                provider="asr",
            )

        await self._ensure_session()

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        file_handle = open(audio_path, "rb")
        try:
            data = aiohttp.FormData()
            data.add_field(
                "file",
                file_handle,
                filename=audio_path.name,
                content_type="audio/wav",
            )
            data.add_field("model", self.model)
            if self.language:
                data.add_field("language", self.language)
            data.add_field("response_format", "text")

            async with self.session.post(
                f"{self.api_url}/audio/transcriptions",
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                elapsed = time.time() - start_time

                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "json" in content_type:
                        result = await response.json()
                        text = result.get("text", "")
                    else:
                        text = (await response.text()).strip()

                    return AnalysisResult(
                        success=True,
                        content=text,
                        model=self.model,
                        provider="asr",
                        inference_time=elapsed,
                    )
                else:
                    error_text = await response.text()
                    return AnalysisResult(
                        success=False,
                        error=f"ASR API error {response.status}: {error_text[:200]}",
                        provider="asr",
                        inference_time=elapsed,
                    )
        except asyncio.TimeoutError:
            return AnalysisResult(
                success=False,
                error=f"ASR request timed out after {self.timeout}s",
                provider="asr",
                inference_time=time.time() - start_time,
            )
        except Exception as e:
            return AnalysisResult(
                success=False,
                error=f"ASR request failed: {e}",
                provider="asr",
                inference_time=time.time() - start_time,
            )
        finally:
            file_handle.close()

    async def health_check(self) -> bool:
        """Check if the ASR service is reachable."""
        try:
            await self._ensure_session()
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            async with self.session.get(
                f"{self.api_url}/models",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                return response.status == 200
        except Exception:
            return False


def create_client(provider: str, **kwargs) -> BaseLLMClient:
    """Create a client for the specified provider"""
    providers = {
        "ollama": OllamaClient,
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
    }

    if provider not in providers:
        raise ValueError(f"Unsupported provider: {provider}")

    return providers[provider](**kwargs)
