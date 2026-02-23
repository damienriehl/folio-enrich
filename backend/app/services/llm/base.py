from __future__ import annotations

import abc
from typing import Any

from app.models.llm_models import ModelInfo


class LLMProvider(abc.ABC):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abc.abstractmethod
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Single-turn text completion."""

    @abc.abstractmethod
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Multi-turn chat completion."""

    @abc.abstractmethod
    async def structured(
        self, prompt: str, schema: dict, **kwargs: Any
    ) -> dict:
        """Completion with JSON output conforming to schema."""

    @abc.abstractmethod
    async def test_connection(self) -> bool:
        """Test connectivity to the provider. Returns True on success."""

    @abc.abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List available models from the provider API."""
