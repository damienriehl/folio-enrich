from __future__ import annotations

import logging
from typing import Any

import httpx

from app.models.llm_models import ModelInfo
from app.services.llm.openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)

_GITHUB_CATALOG_URL = "https://models.github.ai/catalog/models"


class GitHubModelsProvider(OpenAICompatProvider):
    """GitHub Models — extends OpenAI-compatible with GitHub catalog model listing."""

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    _GITHUB_CATALOG_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key or ''}",
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            models = []
            items = data if isinstance(data, list) else data.get("models", data.get("value", []))
            for m in items:
                model_id = m.get("id") or m.get("name", "")
                if not model_id:
                    continue
                display = m.get("friendly_name") or m.get("displayName") or model_id
                models.append(ModelInfo(id=model_id, name=display))
            return sorted(models, key=lambda m: m.id) if models else await super().list_models()
        except Exception:
            logger.debug("Failed to list GitHub Models from catalog, falling back to OpenAI compat", exc_info=True)
            return await super().list_models()
