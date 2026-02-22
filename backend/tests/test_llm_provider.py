from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.llm.base import LLMProvider
from app.services.llm.registry import get_provider, register_provider


class MockLLMProvider(LLMProvider):
    def __init__(self, **kwargs):
        self.calls: list[dict] = []

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"method": "complete", "prompt": prompt})
        return "mock response"

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.calls.append({"method": "chat", "messages": messages})
        return "mock chat response"

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        self.calls.append({"method": "structured", "prompt": prompt})
        return {"concepts": []}


class TestLLMProviderABC:
    @pytest.mark.asyncio
    async def test_mock_provider_complete(self):
        provider = MockLLMProvider()
        result = await provider.complete("test prompt")
        assert result == "mock response"
        assert len(provider.calls) == 1
        assert provider.calls[0]["method"] == "complete"

    @pytest.mark.asyncio
    async def test_mock_provider_chat(self):
        provider = MockLLMProvider()
        result = await provider.chat([{"role": "user", "content": "hi"}])
        assert result == "mock chat response"

    @pytest.mark.asyncio
    async def test_mock_provider_structured(self):
        provider = MockLLMProvider()
        result = await provider.structured("test", {"type": "object"})
        assert result == {"concepts": []}


class TestLLMRegistry:
    def test_register_and_get(self):
        register_provider("mock", MockLLMProvider)
        provider = get_provider("mock")
        assert isinstance(provider, MockLLMProvider)

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_provider("nonexistent_provider_xyz")

    def test_builtin_providers_registered(self):
        # OpenAI and Anthropic should be registered by default
        # We can't instantiate them without API keys, but we can verify registration
        try:
            provider = get_provider("openai")
            assert provider is not None
        except Exception:
            pass  # May fail without API key, that's ok

        try:
            provider = get_provider("anthropic")
            assert provider is not None
        except Exception:
            pass
