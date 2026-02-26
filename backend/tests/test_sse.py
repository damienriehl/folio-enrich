import json

import pytest

from app.models.document import CanonicalText, DocumentFormat, DocumentInput, TextChunk
from app.models.job import Job, JobResult, JobStatus
from app.services.streaming.sse import job_event_stream
from app.storage.job_store import JobStore


class TestSSEEventStream:
    @pytest.mark.asyncio
    async def test_completed_job_emits_status_and_complete(self, tmp_path):
        store = JobStore(base_dir=tmp_path / "jobs")
        job = Job(
            input=DocumentInput(content="test", format=DocumentFormat.PLAIN_TEXT),
            status=JobStatus.COMPLETED,
            result=JobResult(
                canonical_text=CanonicalText(full_text="test", chunks=[]),
            ),
        )
        await store.save(job)

        events = []
        async for event in job_event_stream(job.id, store):
            events.append(event)
            if event.get("event") == "complete":
                break

        assert any(e["event"] == "status" for e in events)
        assert any(e["event"] == "complete" for e in events)

        complete_event = next(e for e in events if e["event"] == "complete")
        data = json.loads(complete_event["data"])
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_nonexistent_job_emits_error(self, tmp_path):
        store = JobStore(base_dir=tmp_path / "jobs")
        from uuid import uuid4

        events = []
        async for event in job_event_stream(uuid4(), store):
            events.append(event)
            break

        assert len(events) == 1
        assert events[0]["event"] == "error"

    @pytest.mark.asyncio
    async def test_document_type_event_emitted(self, tmp_path):
        store = JobStore(base_dir=tmp_path / "jobs")
        job = Job(
            input=DocumentInput(content="test", format=DocumentFormat.PLAIN_TEXT),
            status=JobStatus.COMPLETED,
            result=JobResult(
                canonical_text=CanonicalText(full_text="test", chunks=[]),
                metadata={
                    "document_type": "Motion to Dismiss",
                    "document_type_confidence": 0.92,
                },
            ),
        )
        await store.save(job)

        events = []
        async for event in job_event_stream(job.id, store):
            events.append(event)
            if event.get("event") == "complete":
                break

        dt_events = [e for e in events if e["event"] == "document_type"]
        assert len(dt_events) == 1
        data = json.loads(dt_events[0]["data"])
        assert data["document_type"] == "Motion to Dismiss"
        assert data["confidence"] == 0.92
