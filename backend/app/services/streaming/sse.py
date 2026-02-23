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
    last_states: dict[str, str] = {}
    last_activity_count: int = 0

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
                    "error": job.error,
                }),
            }
            return

        await asyncio.sleep(poll_interval)
