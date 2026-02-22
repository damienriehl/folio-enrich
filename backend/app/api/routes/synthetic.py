from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.testing.synthetic_generator import DOC_TYPES, SyntheticGenerator
from app.services.llm.registry import get_provider
from app.config import settings

router = APIRouter(prefix="/synthetic", tags=["synthetic"])


class SyntheticRequest(BaseModel):
    doc_type: str = "Motion to Dismiss"
    length: str = "medium"
    jurisdiction: str = "Federal"


@router.post("")
async def generate_synthetic(req: SyntheticRequest) -> dict:
    try:
        llm = get_provider(settings.llm_provider, model=settings.llm_model)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM provider unavailable: {e}")

    generator = SyntheticGenerator(llm)
    text = await generator.generate(req.doc_type, req.length, req.jurisdiction)
    return {"document": text, "doc_type": req.doc_type, "length": req.length}


@router.get("/types")
async def list_doc_types() -> dict:
    return {"types": DOC_TYPES}
