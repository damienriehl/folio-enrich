from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.export.registry import get_exporter, list_formats
from app.storage.job_store import JobStore

router = APIRouter(prefix="/enrich", tags=["export"])

_job_store = JobStore()


@router.get("/{job_id}/export")
async def export_job(job_id: UUID, format: str = "json") -> Response:
    job = await _job_store.load(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        exporter = get_exporter(format)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Available: {list_formats()}",
        )

    content = exporter.export(job)
    return Response(
        content=content if isinstance(content, bytes) else content.encode(),
        media_type=exporter.content_type,
    )
