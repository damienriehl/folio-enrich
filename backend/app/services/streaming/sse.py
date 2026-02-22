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
    last_annotation_count = 0

    while True:
        job = await job_store.load(job_id)
        if job is None:
            yield {"event": "error", "data": json.dumps({"error": "Job not found"})}
            return

        # Emit status changes
        if job.status != last_status:
            last_status = job.status
            yield {
                "event": "status",
                "data": json.dumps({
                    "job_id": str(job.id),
                    "status": job.status.value,
                }),
            }

        # Emit new annotations incrementally
        current_count = len(job.result.annotations)
        if current_count > last_annotation_count:
            new_annotations = job.result.annotations[last_annotation_count:]
            for ann in new_annotations:
                yield {
                    "event": "annotation",
                    "data": json.dumps({
                        "span": {"start": ann.span.start, "end": ann.span.end, "text": ann.span.text},
                        "concepts": [c.model_dump() for c in ann.concepts],
                    }),
                }
            last_annotation_count = current_count

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
