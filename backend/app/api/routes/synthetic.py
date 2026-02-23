from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.routes.settings import _get_api_key_for_provider
from app.config import settings
from app.models.llm_models import LLMProviderType
from app.services.llm.registry import get_provider
from app.services.testing.synthetic_generator import DOC_TYPES, SyntheticGenerator

router = APIRouter(prefix="/synthetic", tags=["synthetic"])


class SyntheticRequest(BaseModel):
    doc_type: str = "Motion to Dismiss"
    length: str = "medium"
    jurisdiction: str = "Federal"


@router.post("")
async def generate_synthetic(req: SyntheticRequest) -> dict:
    try:
        provider_name = settings.llm_provider.replace("-", "_")
        if provider_name == "lm_studio":
            provider_name = "lmstudio"
        provider_type = LLMProviderType(provider_name)
        api_key = _get_api_key_for_provider(provider_type)
        llm = get_provider(
            provider_type,
            api_key=api_key,
            model=settings.llm_model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM provider unavailable: {e}")

    generator = SyntheticGenerator(llm)
    text = await generator.generate(req.doc_type, req.length, req.jurisdiction)
    return {"document": text, "doc_type": req.doc_type, "length": req.length}


@router.get("/types")
async def list_doc_types() -> dict:
    return {"types": DOC_TYPES}
