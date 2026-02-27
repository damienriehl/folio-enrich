from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.models.job import Job, JobStatus
from app.storage.job_store import JobStore

logger = logging.getLogger(__name__)


async def job_event_stream(
    job_id, job_store: JobStore, poll_interval: float = 0.5
) -> AsyncGenerator[dict, None]:
    """Generate SSE events as a job progresses through pipeline stages."""
    last_status = None
    seen_ids: set[str] = set()
    seen_individual_ids: set[str] = set()
    seen_property_ids: set[str] = set()
    last_states: dict[str, str] = {}
    last_activity_count: int = 0
    doc_type_sent: bool = False

    while True:
        job = await job_store.load(job_id)
        if job is None:
            yield {"event": "error", "data": json.dumps({"error": "Job not found"})}
            return

        # Emit status changes
        if job.status != last_status:
            last_status = job.status
            status_payload: dict = {
                "job_id": str(job.id),
                "status": job.status.value,
            }
            # Send normalized text once so frontend can align spans
            if job.result.canonical_text is not None and "normalized_text_sent" not in last_states:
                status_payload["canonical_text"] = job.result.canonical_text.full_text
                last_states["normalized_text_sent"] = "yes"
            yield {
                "event": "status",
                "data": json.dumps(status_payload),
            }

        # Emit new and updated annotations using ID-based tracking
        for ann in job.result.annotations:
            ann_id = ann.id
            ann_state = ann.state
            ann_data = {
                "id": ann_id,
                "span": {"start": ann.span.start, "end": ann.span.end, "text": ann.span.text},
                "concepts": [c.model_dump() for c in ann.concepts],
                "state": ann_state,
            }

            if ann_id not in seen_ids:
                # New annotation
                seen_ids.add(ann_id)
                last_states[ann_id] = ann_state
                event_type = "preliminary_annotation" if ann_state == "preliminary" else "annotation"
                yield {"event": event_type, "data": json.dumps(ann_data)}
            elif last_states.get(ann_id) != ann_state:
                # State changed
                last_states[ann_id] = ann_state
                yield {"event": "annotation_update", "data": json.dumps(ann_data)}

        # Emit annotation_removed for annotations that disappeared (e.g., rejected by Resolution)
        current_ids = {ann.id for ann in job.result.annotations}
        removed_ids = seen_ids - current_ids
        for rid in removed_ids:
            yield {"event": "annotation_removed", "data": json.dumps({"id": rid})}
            last_states.pop(rid, None)
        seen_ids -= removed_ids

        # Emit new individuals
        for ind in job.result.individuals:
            if ind.id not in seen_individual_ids:
                seen_individual_ids.add(ind.id)
                ind_data = {
                    "id": ind.id,
                    "name": ind.name,
                    "mention_text": ind.mention_text,
                    "individual_type": ind.individual_type,
                    "span": {"start": ind.span.start, "end": ind.span.end, "text": ind.span.text},
                    "class_links": [
                        {
                            "annotation_id": cl.annotation_id,
                            "folio_iri": cl.folio_iri,
                            "folio_label": cl.folio_label,
                            "branch": cl.branch,
                            "confidence": cl.confidence,
                        }
                        for cl in ind.class_links
                    ],
                    "confidence": ind.confidence,
                    "source": ind.source,
                    "normalized_form": ind.normalized_form,
                    "url": ind.url,
                }
                yield {"event": "individual_added", "data": json.dumps(ind_data)}

        # Emit new properties
        for prop in job.result.properties:
            if prop.id not in seen_property_ids:
                seen_property_ids.add(prop.id)
                prop_data = {
                    "id": prop.id,
                    "property_text": prop.property_text,
                    "folio_iri": prop.folio_iri,
                    "folio_label": prop.folio_label,
                    "folio_definition": prop.folio_definition,
                    "span": {"start": prop.span.start, "end": prop.span.end, "text": prop.span.text},
                    "domain_iris": prop.domain_iris,
                    "range_iris": prop.range_iris,
                    "inverse_of_iri": prop.inverse_of_iri,
                    "confidence": prop.confidence,
                    "source": prop.source,
                    "match_type": prop.match_type,
                }
                yield {"event": "property_added", "data": json.dumps(prop_data)}

        # Emit document type as soon as MetadataStage assigns it
        if not doc_type_sent and job.result.metadata.get("document_type"):
            doc_type_sent = True
            yield {
                "event": "document_type",
                "data": json.dumps({
                    "document_type": job.result.metadata["document_type"],
                    "confidence": job.result.metadata.get("document_type_confidence", 0.0),
                }),
            }

        # Emit new activity log entries
        activity_log = job.result.metadata.get("activity_log", [])
        if len(activity_log) > last_activity_count:
            for entry in activity_log[last_activity_count:]:
                yield {"event": "activity", "data": json.dumps(entry)}
            last_activity_count = len(activity_log)

        # Terminal states
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            yield {
                "event": "complete",
                "data": json.dumps({
                    "job_id": str(job.id),
                    "status": job.status.value,
                    "total_annotations": len(job.result.annotations),
                    "total_individuals": len(job.result.individuals),
                    "total_properties": len(job.result.properties),
                    "error": job.error,
                }),
            }
            return

        await asyncio.sleep(poll_interval)
