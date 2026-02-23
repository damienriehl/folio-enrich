from __future__ import annotations

import json
import logging
from typing import Any

from app.models.llm_models import ModelInfo
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatProvider(LLMProvider):
    """Unified provider for all OpenAI-compatible APIs.

    Handles: openai, mistral, meta_llama, ollama, lmstudio, custom, groq, xai, llamafile.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, model=model)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai

            kwargs: dict[str, Any] = {"api_key": self.api_key or "no-key"}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = openai.AsyncOpenAI(**kwargs)
        return self._client

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return await self.chat(
            [{"role": "user", "content": prompt}], **kwargs
        )

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=kwargs.pop("model", self.model or "gpt-4o-mini"),
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    async def structured(
        self, prompt: str, schema: dict, **kwargs: Any
    ) -> dict:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=kwargs.pop("model", self.model or "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            **kwargs,
        )
        text = response.choices[0].message.content or "{}"
        return json.loads(text)

    async def test_connection(self) -> bool:
        client = self._get_client()
        if self.model:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,
            )
            return bool(response.choices)
        else:
            models = await client.models.list()
            return True

    async def list_models(self) -> list[ModelInfo]:
        try:
            client = self._get_client()
            response = await client.models.list()
            models = []
            for m in response:
                models.append(
                    ModelInfo(id=m.id, name=m.id)
                )
            return sorted(models, key=lambda m: m.id)
        except Exception:
            logger.debug("Failed to list models dynamically", exc_info=True)
            return []
