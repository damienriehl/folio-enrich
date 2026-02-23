from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.models.llm_models import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    LLMProviderType,
    ModelInfo,
    ModelListRequest,
)
from app.services.llm.registry import (
    DEFAULT_MODELS,
    KNOWN_MODELS,
    PROVIDER_DISPLAY_NAMES,
    REQUIRES_API_KEY,
    get_provider,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Map of provider type → settings attribute name for API keys
_API_KEY_ATTRS: dict[LLMProviderType, str] = {
    LLMProviderType.openai: "openai_api_key",
    LLMProviderType.anthropic: "anthropic_api_key",
    LLMProviderType.google: "google_api_key",
    LLMProviderType.mistral: "mistral_api_key",
    LLMProviderType.cohere: "cohere_api_key",
    LLMProviderType.meta_llama: "meta_llama_api_key",
    LLMProviderType.groq: "groq_api_key",
    LLMProviderType.xai: "xai_api_key",
    LLMProviderType.github_models: "github_models_api_key",
}


def _get_api_key_for_provider(
    provider_type: LLMProviderType,
    explicit_key: str | None = None,
) -> str | None:
    """Resolve the API key: explicit > stored in settings > None."""
    if explicit_key:
        return explicit_key
    attr = _API_KEY_ATTRS.get(provider_type)
    if attr:
        return getattr(settings, attr, None) or None
    return None


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    mistral_api_key: str | None = None
    cohere_api_key: str | None = None
    meta_llama_api_key: str | None = None
    groq_api_key: str | None = None
    xai_api_key: str | None = None
    github_models_api_key: str | None = None


@router.get("")
async def get_settings() -> dict:
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "openai_api_key_set": bool(settings.openai_api_key),
        "anthropic_api_key_set": bool(settings.anthropic_api_key),
        "google_api_key_set": bool(settings.google_api_key),
        "mistral_api_key_set": bool(settings.mistral_api_key),
        "cohere_api_key_set": bool(settings.cohere_api_key),
        "meta_llama_api_key_set": bool(settings.meta_llama_api_key),
        "groq_api_key_set": bool(settings.groq_api_key),
        "xai_api_key_set": bool(settings.xai_api_key),
        "github_models_api_key_set": bool(settings.github_models_api_key),
        "max_chunk_chars": settings.max_chunk_chars,
        "chunk_overlap_chars": settings.chunk_overlap_chars,
        "max_upload_size": settings.max_upload_size,
    }


@router.put("")
async def update_settings(update: SettingsUpdate) -> dict:
    if update.llm_provider is not None:
        settings.llm_provider = update.llm_provider
    if update.llm_model is not None:
        settings.llm_model = update.llm_model
    # Update any provided API keys
    for field in (
        "openai_api_key",
        "anthropic_api_key",
        "google_api_key",
        "mistral_api_key",
        "cohere_api_key",
        "meta_llama_api_key",
        "groq_api_key",
        "xai_api_key",
        "github_models_api_key",
    ):
        val = getattr(update, field, None)
        if val is not None:
            setattr(settings, field, val)
    return {"status": "ok", "message": "Settings updated"}


@router.get("/providers")
async def list_providers() -> dict:
    """Return provider metadata: display names, requires_api_key, default models."""
    providers = {}
    for pt in LLMProviderType:
        providers[pt.value] = {
            "display_name": PROVIDER_DISPLAY_NAMES.get(pt, pt.value),
            "requires_api_key": REQUIRES_API_KEY.get(pt, True),
            "default_model": DEFAULT_MODELS.get(pt, ""),
            "api_key_set": bool(
                _get_api_key_for_provider(pt)
            ),
        }
    return {
        "providers": providers,
        "current": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
        },
    }


@router.get("/known-models")
async def get_known_models() -> dict:
    """Return static fallback model lists (no API key needed)."""
    result = {}
    for pt, models in KNOWN_MODELS.items():
        result[pt.value] = [m.model_dump() for m in models]
    return {"models": result}


@router.post("/models")
async def list_models_dynamic(req: ModelListRequest) -> dict:
    """Dynamically list models from a provider's API."""
    api_key = _get_api_key_for_provider(req.provider, req.api_key)

    try:
        provider = get_provider(
            provider_type=req.provider,
            api_key=api_key,
            base_url=req.base_url,
        )
        models = await provider.list_models()
        return {
            "models": [m.model_dump() for m in models],
            "source": "dynamic",
        }
    except Exception as e:
        logger.debug("Dynamic model listing failed for %s: %s", req.provider, e)
        # Fall back to known models
        fallback = KNOWN_MODELS.get(req.provider, [])
        return {
            "models": [m.model_dump() for m in fallback],
            "source": "fallback",
            "error": str(e),
        }


@router.post("/test-connection")
async def test_connection(req: ConnectionTestRequest) -> ConnectionTestResponse:
    """Test an LLM provider connection."""
    api_key = _get_api_key_for_provider(req.provider, req.api_key)

    if REQUIRES_API_KEY.get(req.provider, True) and not api_key:
        return ConnectionTestResponse(
            success=False,
            message=f"No API key for {req.provider.value}",
        )

    try:
        provider = get_provider(
            provider_type=req.provider,
            api_key=api_key,
            base_url=req.base_url,
            model=req.model,
        )
        await provider.test_connection()
        return ConnectionTestResponse(
            success=True,
            message="Connection successful",
            model=req.model or provider.model,
        )
    except Exception as e:
        return ConnectionTestResponse(
            success=False,
            message=str(e),
        )


@router.get("/pricing")
async def get_pricing() -> dict:
    """Return LLM cost-per-document estimates from LiteLLM pricing DB."""
    from app.services.llm.pricing import fetch_pricing

    prices, fetched_at = await fetch_pricing()
    return {
        "prices": prices,
        "fetched_at": fetched_at,
        "model_count": len(prices),
    }
