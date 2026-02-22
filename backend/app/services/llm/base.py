from __future__ import annotations

import abc
from typing import Any


class LLMProvider(abc.ABC):
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
