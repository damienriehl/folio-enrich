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
from app.services.ingestion.registry import detect_format
from app.services.streaming.sse import job_event_stream
from app.storage.job_store import JobStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrich", tags=["enrich"])

_job_store = JobStore()


class EnrichRequest(BaseModel):
    content: str
    format: str | None = None
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

    fmt = req.format or detect_format(req.filename, req.content).value
    doc = DocumentInput(content=req.content, format=fmt, filename=req.filename)
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


@router.get("/{job_id}/annotations/{annotation_id}/lineage")
async def get_annotation_lineage(job_id: UUID, annotation_id: str) -> dict:
    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    for ann in job.result.annotations:
        if ann.id == annotation_id:
            return {
                "annotation_id": annotation_id,
                "lineage": [e.model_dump() for e in ann.lineage],
                "sentence_text": ann.span.sentence_text,
            }
    raise HTTPException(status_code=404, detail="Annotation not found")


class PromoteRequest(BaseModel):
    concept_index: int


class CascadePromoteRequest(BaseModel):
    old_iri: str
    new_iri: str
    annotation_ids: list[str] | None = None


@router.post("/{job_id}/annotations/{annotation_id}/promote")
async def promote_concept(job_id: UUID, annotation_id: str, req: PromoteRequest) -> dict:
    """Promote a backup concept to primary (index 0)."""
    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    for ann in job.result.annotations:
        if ann.id == annotation_id:
            if req.concept_index < 0 or req.concept_index >= len(ann.concepts):
                raise HTTPException(status_code=400, detail="Invalid concept_index")
            if req.concept_index == 0:
                return {"status": "already_primary"}

            # Swap: move selected to position 0
            promoted = ann.concepts.pop(req.concept_index)
            old_primary = ann.concepts[0]
            promoted.state = "confirmed"
            old_primary.state = "backup"
            ann.concepts[0] = promoted
            ann.concepts.insert(req.concept_index, old_primary)

            # Record lineage event
            from app.models.annotation import StageEvent
            ann.lineage.append(StageEvent(
                stage="user",
                action="user_promotion",
                detail=f"Promoted '{promoted.folio_label}' over '{old_primary.folio_label}'",
            ))

            await _job_store.save(job)
            return {
                "status": "promoted",
                "annotation_id": annotation_id,
                "promoted_iri": promoted.folio_iri,
                "demoted_iri": old_primary.folio_iri,
            }

    raise HTTPException(status_code=404, detail="Annotation not found")


@router.post("/{job_id}/cascade-promote")
async def cascade_promote(job_id: UUID, req: CascadePromoteRequest) -> dict:
    """Promote a backup concept across all annotations sharing the old primary IRI."""
    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    from app.models.annotation import StageEvent

    id_filter = set(req.annotation_ids) if req.annotation_ids is not None else None

    updated = 0
    for ann in job.result.annotations:
        if not ann.concepts or ann.concepts[0].folio_iri != req.old_iri:
            continue
        if id_filter is not None and ann.id not in id_filter:
            continue
        # Find backup with new_iri
        backup_idx = None
        for i, c in enumerate(ann.concepts[1:], start=1):
            if c.folio_iri == req.new_iri:
                backup_idx = i
                break
        if backup_idx is None:
            continue

        promoted = ann.concepts.pop(backup_idx)
        old_primary = ann.concepts[0]
        promoted.state = "confirmed"
        old_primary.state = "backup"
        ann.concepts[0] = promoted
        ann.concepts.insert(backup_idx, old_primary)

        ann.lineage.append(StageEvent(
            stage="user",
            action="user_promotion",
            detail=f"Cascade: promoted '{promoted.folio_label}' over '{old_primary.folio_label}'",
        ))
        updated += 1

    if updated > 0:
        await _job_store.save(job)

    return {"status": "cascade_complete", "updated_count": updated}


class BulkRejectRequest(BaseModel):
    folio_iri: str
    comment: str = ""


@router.post("/{job_id}/annotations/{annotation_id}/reject")
async def reject_annotation(job_id: UUID, annotation_id: str) -> dict:
    """Dismiss an annotation as a false positive (set state to rejected)."""
    from datetime import datetime, timezone
    from app.models.annotation import StageEvent

    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    for ann in job.result.annotations:
        if ann.id == annotation_id:
            if ann.state == "rejected":
                return {"status": "already_rejected"}
            prev_state = ann.state
            ann.state = "rejected"
            ann.dismissed_at = datetime.now(timezone.utc).isoformat()
            ann.lineage.append(StageEvent(
                stage="user",
                action="user_rejected",
                detail=f"Dismissed as false positive (was '{prev_state}')",
            ))
            await _job_store.save(job)

            # Count how many other annotations share the same primary IRI
            primary_iri = ann.concepts[0].folio_iri if ann.concepts else None
            same_iri_count = 0
            if primary_iri:
                same_iri_count = sum(
                    1 for a in job.result.annotations
                    if a.id != annotation_id
                    and a.state != "rejected"
                    and a.concepts
                    and a.concepts[0].folio_iri == primary_iri
                )

            return {
                "status": "rejected",
                "annotation_id": annotation_id,
                "same_concept_count": same_iri_count,
                "folio_iri": primary_iri,
            }

    raise HTTPException(status_code=404, detail="Annotation not found")


@router.post("/{job_id}/annotations/{annotation_id}/restore")
async def restore_annotation(job_id: UUID, annotation_id: str) -> dict:
    """Restore a dismissed annotation (set state back to confirmed)."""
    from app.models.annotation import StageEvent

    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    for ann in job.result.annotations:
        if ann.id == annotation_id:
            if ann.state != "rejected":
                return {"status": "not_rejected", "current_state": ann.state}
            ann.state = "confirmed"
            ann.dismissed_at = None
            ann.lineage.append(StageEvent(
                stage="user",
                action="user_restored",
                detail="Restored from dismissed state",
            ))
            await _job_store.save(job)
            return {"status": "restored", "annotation_id": annotation_id}

    raise HTTPException(status_code=404, detail="Annotation not found")


@router.post("/{job_id}/annotations/bulk-reject")
async def bulk_reject_annotations(job_id: UUID, req: BulkRejectRequest) -> dict:
    """Dismiss all annotations sharing the same primary FOLIO IRI."""
    from datetime import datetime, timezone
    from app.models.annotation import StageEvent

    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    rejected_ids = []
    for ann in job.result.annotations:
        if ann.state == "rejected":
            continue
        if not ann.concepts or ann.concepts[0].folio_iri != req.folio_iri:
            continue
        ann.state = "rejected"
        ann.dismissed_at = now
        ann.lineage.append(StageEvent(
            stage="user",
            action="user_rejected",
            detail=f"Bulk dismissed as false positive",
        ))
        rejected_ids.append(ann.id)
        updated += 1

    if updated > 0:
        await _job_store.save(job)

    return {
        "status": "bulk_rejected",
        "updated_count": updated,
        "rejected_ids": rejected_ids,
    }


@router.get("/{job_id}/stream")
async def stream_enrichment(job_id: UUID):
    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return EventSourceResponse(job_event_stream(job_id, _job_store))
