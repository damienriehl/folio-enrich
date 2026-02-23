from __future__ import annotations

import json
import logging
from typing import Any

from app.models.llm_models import ModelInfo
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Fallback list used when the models API is unreachable.
# Ordered: oldest/cheapest → newest/most powerful.
_FALLBACK_MODELS: list[ModelInfo] = [
    ModelInfo(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5", context_window=200000),
    ModelInfo(id="claude-sonnet-4-5-20250929", name="Claude Sonnet 4.5", context_window=200000),
    ModelInfo(id="claude-sonnet-4-6", name="Claude Sonnet 4.6", context_window=200000),
    ModelInfo(id="claude-opus-4-6", name="Claude Opus 4.6", context_window=200000),
]


class AnthropicProvider(LLMProvider):
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

        # Separate system message from user/assistant messages
        system_msg = None
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                chat_messages.append(msg)

        create_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", self.model or "claude-sonnet-4-6"),
            "max_tokens": max_tokens,
            "messages": chat_messages or [{"role": "user", "content": ""}],
        }
        if system_msg:
            create_kwargs["system"] = system_msg

        create_kwargs.update(kwargs)
        response = await client.messages.create(**create_kwargs)
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
            text = "\n".join(
                lines[1:-1] if lines[-1].startswith("```") else lines[1:]
            )
        return json.loads(text)

    async def test_connection(self) -> bool:
        client = self._get_client()
        response = await client.messages.create(
            model=self.model or "claude-sonnet-4-6",
            max_tokens=1,
            messages=[{"role": "user", "content": "Hi"}],
        )
        return bool(response.content)

    async def list_models(self) -> list[ModelInfo]:
        try:
            client = self._get_client()
            models = []
            response = await client.models.list(limit=100)
            for m in response.data:
                models.append(
                    ModelInfo(
                        id=m.id,
                        name=getattr(m, "display_name", m.id),
                    )
                )
            return sorted(models, key=lambda m: m.id) if models else _FALLBACK_MODELS
        except Exception:
            logger.debug("Failed to list Anthropic models dynamically, using fallback", exc_info=True)
            return _FALLBACK_MODELS
