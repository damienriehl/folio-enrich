from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.models.llm_models import ModelInfo
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class CohereProvider(LLMProvider):
    """Cohere provider using the REST API via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, model=model)
        self._base = (base_url or "https://api.cohere.com/v2").rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}",
        }

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return await self.chat(
            [{"role": "user", "content": prompt}], **kwargs
        )

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        model = kwargs.pop("model", self.model or "command-r-plus")

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        url = f"{self._base}/chat"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()

        # Cohere v2 chat response
        message = data.get("message", {})
        content = message.get("content", [])
        if content:
            return content[0].get("text", "")
        return ""

    async def structured(
        self, prompt: str, schema: dict, **kwargs: Any
    ) -> dict:
        prompt_with_json = (
            f"{prompt}\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        text = await self.complete(prompt_with_json, **kwargs)
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                lines[1:-1] if lines[-1].startswith("```") else lines[1:]
            )
        return json.loads(text)

    async def test_connection(self) -> bool:
        model = self.model or "command-r-plus"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
        }
        url = f"{self._base}/chat"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
        return True

    async def list_models(self) -> list[ModelInfo]:
        try:
            # Cohere v2 models endpoint
            url = f"{self._base}/models"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()

            models = []
            for m in data.get("models", []):
                model_id = m.get("name", "")
                if not model_id:
                    continue
                ctx = m.get("context_length")
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_id,
                        context_window=ctx,
                    )
                )
            return sorted(models, key=lambda m: m.id)
        except Exception:
            logger.debug("Failed to list Cohere models dynamically", exc_info=True)
            return []
