from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.models.document import DocumentInput
from app.models.job import Job, JobStatus
from app.pipeline.orchestrator import PipelineOrchestrator, TaskLLMs
from app.services.streaming.sse import job_event_stream
from app.storage.job_store import JobStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrich", tags=["enrich"])

_job_store = JobStore()


class EnrichRequest(BaseModel):
    content: str
    format: str = "plain_text"
    filename: str | None = None
    # Optional per-request LLM configuration
    llm_provider: str | None = None
    llm_model: str | None = None
    api_key: str | None = None


def _get_llm_for_request(req: EnrichRequest):
    """Create an LLM provider from request params or fall back to settings."""
    from app.config import settings
    from app.services.llm.registry import REQUIRES_API_KEY, get_provider
    from app.api.routes.settings import _get_api_key_for_provider
    from app.models.llm_models import LLMProviderType

    provider_name = req.llm_provider or settings.llm_provider
    model = req.llm_model or settings.llm_model

    # Normalize provider name to enum
    try:
        normalized = provider_name.replace("-", "_")
        if normalized == "lm_studio":
            normalized = "lmstudio"
        provider_type = LLMProviderType(normalized)
    except ValueError:
        logger.warning("Unknown provider %s — LLM stages will be skipped", provider_name)
        return None

    api_key = _get_api_key_for_provider(provider_type, req.api_key)

    if REQUIRES_API_KEY.get(provider_type, True) and not api_key:
        logger.info("No API key for %s — LLM stages will be skipped", provider_name)
        return None

    try:
        return get_provider(provider_type, api_key=api_key, model=model)
    except Exception:
        logger.warning("Failed to create LLM provider %s", provider_name, exc_info=True)
        return None


@router.post("", status_code=202)
async def create_enrichment(req: EnrichRequest) -> dict:
    # Check concurrent job limit
    from app.config import settings as app_settings
    active = await _job_store.count_active()
    if active >= app_settings.max_concurrent_jobs:
        raise HTTPException(
            status_code=429,
            detail=f"Too many concurrent jobs ({active}/{app_settings.max_concurrent_jobs}). Try again later.",
        )

    doc = DocumentInput(content=req.content, format=req.format, filename=req.filename)
    job = Job(input=doc)
    await _job_store.save(job)

    # Build pipeline with per-task LLMs (task-specific overrides > request > global)
    fallback_llm = _get_llm_for_request(req)
    task_llms = TaskLLMs.from_settings(fallback=fallback_llm)
    orchestrator = PipelineOrchestrator(_job_store, llm=fallback_llm, task_llms=task_llms)

    # Run pipeline in background
    asyncio.create_task(orchestrator.run(job))
    return {"job_id": str(job.id), "status": job.status.value}


@router.get("/branches")
async def list_branches() -> dict:
    """Return all non-excluded FOLIO branches with colors and concept counts."""
    from app.services.folio.folio_service import FolioService

    service = FolioService.get_instance()
    branches = service.get_all_branches()
    return {"branches": branches, "total": len(branches)}


@router.get("/{job_id}")
async def get_enrichment(job_id: UUID) -> Job:
    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/stream")
async def stream_enrichment(job_id: UUID):
    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return EventSourceResponse(job_event_stream(job_id, _job_store))
