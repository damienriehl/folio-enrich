from __future__ import annotations

import logging

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/detail")
async def health_detail() -> dict:
    """Detailed health check for all subsystems."""
    result = {
        "backend": {"status": "ok"},
        "folio_ontology": _check_folio(),
        "embedding": _check_embedding(),
        "llm": _check_llm(),
        "spacy": _check_spacy(),
    }
    return result


def _check_folio() -> dict:
    try:
        from app.services.folio.folio_service import FolioService
        from app.services.folio.owl_cache import get_owl_status
        svc = FolioService.get_instance()
        if svc._folio is not None:
            count = len(svc._folio.classes)
            label_count = len(svc._labels_cache) if svc._labels_cache else 0
            return {
                "status": "ready",
                "concepts": count,
                "labels_indexed": label_count,
                "owl_cache": get_owl_status(),
            }
        else:
            return {"status": "not_loaded", "message": "Loaded at startup"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _check_embedding() -> dict:
    try:
        from app.services.embedding.service import EmbeddingService
        svc = EmbeddingService.get_instance()
        if svc._provider is not None:
            provider_name = type(svc._provider).__name__
            return {
                "status": "ready",
                "provider": provider_name,
                "index_size": svc.index_size,
            }
        else:
            return {"status": "not_loaded", "message": "Loaded at startup"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _check_llm() -> dict:
    provider = settings.llm_provider
    model = settings.llm_model

    # Map provider name → settings attribute for API key
    _KEY_ATTRS = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "google": "google_api_key",
        "mistral": "mistral_api_key",
        "cohere": "cohere_api_key",
        "meta_llama": "meta_llama_api_key",
        "groq": "groq_api_key",
        "xai": "xai_api_key",
        "github_models": "github_models_api_key",
    }
    # Local providers never need an API key
    _LOCAL_PROVIDERS = {"ollama", "lmstudio", "lm_studio", "custom", "llamafile"}

    if provider in _LOCAL_PROVIDERS:
        has_key = True
    else:
        attr = _KEY_ATTRS.get(provider)
        has_key = bool(getattr(settings, attr, "")) if attr else False

    if has_key:
        return {
            "status": "configured",
            "provider": provider,
            "model": model,
        }
    else:
        return {
            "status": "no_api_key",
            "provider": provider,
            "model": model,
            "message": f"No API key set for {provider}",
        }


def _check_spacy() -> dict:
    try:
        import spacy
        from app.services.entity_ruler.ruler import FOLIOEntityRuler
        return {
            "status": "ready",
            "version": spacy.__version__,
        }
    except ImportError:
        return {"status": "error", "message": "spaCy not installed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
