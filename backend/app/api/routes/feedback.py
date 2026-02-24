from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.models.annotation import FeedbackItem
from app.models.feedback import FeedbackEntry, InsightsSummary
from app.storage.feedback_store import FeedbackStore
from app.storage.job_store import JobStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

_feedback_store = FeedbackStore()
_job_store = JobStore()


class FeedbackRequest(BaseModel):
    job_id: str
    annotation_id: str
    rating: str  # "up" or "down"
    stage: str | None = None
    comment: str = ""


@router.post("", status_code=201)
async def submit_feedback(req: FeedbackRequest) -> dict:
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating must be 'up' or 'down'")

    # Load job and find annotation
    try:
        job_uuid = UUID(req.job_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid job_id format")

    job = await _job_store.load(job_uuid)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    annotation = None
    for ann in job.result.annotations:
        if ann.id == req.annotation_id:
            annotation = ann
            break
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")

    now = datetime.now(timezone.utc).isoformat()
    concept = annotation.concepts[0] if annotation.concepts else None

    # Upsert: one feedback entry per annotation — update if exists, create if not
    existing = await _feedback_store.find_by_annotation(req.job_id, req.annotation_id)
    if existing:
        # Update existing entry
        existing.rating = req.rating
        if req.stage:
            existing.stage = req.stage
        if req.comment:
            existing.comment = req.comment
        existing.created_at = now
        await _feedback_store.save(existing)
        entry_id = existing.id
    else:
        # Create new entry with lineage snapshot
        feedback_item = FeedbackItem(
            rating=req.rating,
            stage=req.stage,
            comment=req.comment,
            created_at=now,
        )
        entry = FeedbackEntry(
            id=feedback_item.id,
            job_id=req.job_id,
            annotation_id=req.annotation_id,
            rating=req.rating,
            stage=req.stage,
            comment=req.comment,
            annotation_text=annotation.span.text,
            sentence_text=annotation.span.sentence_text,
            folio_iri=concept.folio_iri if concept else None,
            folio_label=concept.folio_label if concept else None,
            lineage=[e.model_dump() for e in annotation.lineage],
            created_at=now,
        )
        await _feedback_store.save(entry)
        entry_id = entry.id

    # Also update inline feedback on the annotation (replace, not append)
    annotation.feedback = [FeedbackItem(
        id=entry_id,
        rating=req.rating,
        stage=req.stage,
        comment=req.comment,
        created_at=now,
    )]
    await _job_store.save(job)

    return {"id": entry_id, "status": "saved"}


@router.get("/insights", response_model=InsightsSummary)
async def get_insights() -> InsightsSummary:
    return await _feedback_store.get_insights()


@router.get("/insights/{job_id}", response_model=InsightsSummary)
async def get_job_insights(job_id: str) -> InsightsSummary:
    return await _feedback_store.get_insights(job_id=job_id)


@router.get("/export")
async def export_feedback(format: str = Query("json", pattern="^(json|csv)$")) -> Response:
    """Export all feedback + lineage snapshots as JSON or CSV."""
    entries = await _feedback_store.list_all()

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "job_id", "annotation_id", "rating", "stage", "comment",
            "annotation_text", "folio_iri", "folio_label", "lineage", "created_at",
        ])
        for e in entries:
            # Serialize lineage as compact JSON string within the CSV cell
            lineage_json = json.dumps(e.lineage) if e.lineage else ""
            writer.writerow([
                e.id, e.job_id, e.annotation_id, e.rating, e.stage or "",
                e.comment, e.annotation_text, e.folio_iri or "", e.folio_label or "",
                lineage_json, e.created_at,
            ])
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=feedback.csv"},
        )

    # JSON (default)
    data = [e.model_dump() for e in entries]
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=feedback.json"},
    )


@router.delete("", status_code=200)
async def clear_all_feedback() -> dict:
    """Clear all persisted feedback."""
    count = await _feedback_store.delete_all()
    return {"deleted": count}


@router.delete("/{feedback_id}", status_code=200)
async def delete_feedback(feedback_id: str) -> dict:
    """Delete a single feedback entry."""
    deleted = await _feedback_store.delete(feedback_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Feedback entry not found")
    return {"deleted": 1}
