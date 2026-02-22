from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.models.document import DocumentInput
from app.models.job import Job, JobStatus
from app.pipeline.orchestrator import PipelineOrchestrator
from app.services.streaming.sse import job_event_stream
from app.storage.job_store import JobStore

router = APIRouter(prefix="/enrich", tags=["enrich"])

_job_store = JobStore()
_orchestrator = PipelineOrchestrator(_job_store)


@router.post("", status_code=202)
async def create_enrichment(doc: DocumentInput) -> dict:
    job = Job(input=doc)
    await _job_store.save(job)
    # Run pipeline in background
    asyncio.create_task(_orchestrator.run(job))
    return {"job_id": str(job.id), "status": job.status.value}


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
