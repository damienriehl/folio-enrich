from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.models.llm_models import ModelInfo
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class GoogleProvider(LLMProvider):
    """Google Gemini provider using the REST API via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, model=model)
        self._base = (base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key or "",
        }

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return await self.chat(
            [{"role": "user", "content": prompt}], **kwargs
        )

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        model = kwargs.pop("model", self.model or "gemini-2.0-flash")

        # Separate system instruction from conversation
        system_parts = []
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system_parts.append(text)
            else:
                # Gemini uses "user" and "model" roles
                gemini_role = "model" if role == "assistant" else "user"
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": text}],
                })

        body: dict[str, Any] = {"contents": contents}
        if system_parts:
            body["system_instruction"] = {
                "parts": [{"text": "\n".join(system_parts)}]
            }

        url = f"{self._base}/models/{model}:generateContent"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return parts[0].get("text", "") if parts else ""
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
        model = self.model or "gemini-2.0-flash"
        url = f"{self._base}/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
        return True

    async def list_models(self) -> list[ModelInfo]:
        try:
            url = f"{self._base}/models"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()

            models = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in methods:
                    continue
                model_id = m.get("name", "").replace("models/", "")
                if not model_id:
                    continue
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=m.get("displayName", model_id),
                        context_window=m.get("inputTokenLimit"),
                    )
                )
            return sorted(models, key=lambda m: m.id)
        except Exception:
            logger.debug("Failed to list Google models dynamically", exc_info=True)
            return []
