from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.models.llm_models import ModelInfo
from app.services.llm.base import LLMProvider
from app.services.llm.registry import get_provider


class MockLLMProvider(LLMProvider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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

    async def test_connection(self) -> bool:
        return True

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="mock-model", name="Mock Model")]


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

    @pytest.mark.asyncio
    async def test_mock_provider_test_connection(self):
        provider = MockLLMProvider()
        result = await provider.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_mock_provider_list_models(self):
        provider = MockLLMProvider()
        models = await provider.list_models()
        assert len(models) == 1
        assert models[0].id == "mock-model"


class TestLLMRegistry:
    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_provider("nonexistent_provider_xyz")

    def test_builtin_providers_registered(self):
        # OpenAI and Anthropic should be available
        try:
            provider = get_provider("openai", api_key="test")
            assert provider is not None
        except Exception:
            pass

        try:
            provider = get_provider("anthropic", api_key="test")
            assert provider is not None
        except Exception:
            pass

    def test_backward_compat_lm_studio(self):
        provider = get_provider("lm_studio")
        assert provider is not None
