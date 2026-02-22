from __future__ import annotations

import json
import os
from typing import Any

from app.services.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return await self.chat(
            [{"role": "user", "content": prompt}], **kwargs
        )

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        client = self._get_client()
        max_tokens = kwargs.pop("max_tokens", 4096)
        response = await client.messages.create(
            model=kwargs.pop("model", self.model),
            max_tokens=max_tokens,
            messages=messages,
            **kwargs,
        )
        return response.content[0].text if response.content else ""

    async def structured(
        self, prompt: str, schema: dict, **kwargs: Any
    ) -> dict:
        prompt_with_json = (
            f"{prompt}\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        text = await self.complete(prompt_with_json, **kwargs)
        # Extract JSON from response (handle markdown code blocks)
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        return json.loads(text)
