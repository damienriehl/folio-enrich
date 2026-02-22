from __future__ import annotations

import json
import os
from typing import Any

from app.services.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai

            kwargs = {"api_key": self.api_key}
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
            model=kwargs.pop("model", self.model),
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    async def structured(
        self, prompt: str, schema: dict, **kwargs: Any
    ) -> dict:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=kwargs.pop("model", self.model),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            **kwargs,
        )
        text = response.choices[0].message.content or "{}"
        return json.loads(text)
