from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


PROVIDER_MODELS = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o3-mini",
    ],
    "anthropic": [
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
    ],
    "ollama": [
        "llama3.2",
        "llama3.1",
        "mistral",
        "codellama",
        "gemma2",
    ],
    "lm_studio": [
        "local-model",
    ],
}


@router.get("")
async def get_settings() -> dict:
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "openai_api_key_set": bool(settings.openai_api_key),
        "anthropic_api_key_set": bool(settings.anthropic_api_key),
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
    if update.openai_api_key is not None:
        settings.openai_api_key = update.openai_api_key
    if update.anthropic_api_key is not None:
        settings.anthropic_api_key = update.anthropic_api_key
    return {"status": "ok", "message": "Settings updated"}


@router.get("/providers")
async def list_providers() -> dict:
    return {
        "providers": PROVIDER_MODELS,
        "current": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
        },
    }


@router.post("/test-connection")
async def test_connection(provider: str = "openai", model: str = "gpt-4o-mini", api_key: str = "") -> dict:
    """Test an LLM provider connection."""
    from app.services.llm.registry import get_provider

    actual_key = api_key
    if not actual_key:
        if provider == "openai":
            actual_key = settings.openai_api_key
        elif provider == "anthropic":
            actual_key = settings.anthropic_api_key

    if not actual_key:
        return {"status": "error", "message": f"No API key for {provider}"}

    try:
        llm = get_provider(provider, model=model, api_key=actual_key)
        response = await llm.complete("Say 'connection successful' in exactly two words.")
        return {"status": "ok", "message": "Connection successful", "response": response[:100]}
    except Exception as e:
        return {"status": "error", "message": str(e)}
