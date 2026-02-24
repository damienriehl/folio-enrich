"""Tests for feedback storage and API endpoints."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.annotation import Annotation, ConceptMatch, FeedbackItem, Span, StageEvent
from app.models.feedback import FeedbackEntry, InsightsSummary
from app.models.job import Job, JobStatus
from app.models.document import DocumentInput
from app.storage.feedback_store import FeedbackStore
from app.storage.job_store import JobStore


class TestFeedbackEntryModel:
    def test_create_feedback_entry(self):
        entry = FeedbackEntry(
            id="fb-1",
            job_id="job-1",
            annotation_id="ann-1",
            rating="down",
            stage="entity_ruler",
            comment="Wrong match",
            annotation_text="Contract",
            folio_iri="http://example.com/contract",
            folio_label="Contract",
            created_at="2025-01-01T00:00:00+00:00",
        )
        assert entry.rating == "down"
        assert entry.stage == "entity_ruler"

    def test_create_with_lineage_snapshot(self):
        entry = FeedbackEntry(
            id="fb-1",
            job_id="job-1",
            annotation_id="ann-1",
            rating="down",
            annotation_text="Contract",
            lineage=[
                {"stage": "entity_ruler", "action": "created", "detail": "Matched preferred label"},
                {"stage": "reconciliation", "action": "confirmed", "detail": "Both agree"},
            ],
            created_at="2025-01-01T00:00:00+00:00",
        )
        assert len(entry.lineage) == 2
        assert entry.lineage[0]["stage"] == "entity_ruler"
        assert entry.lineage[1]["action"] == "confirmed"

    def test_default_lineage_is_empty(self):
        entry = FeedbackEntry(
            id="fb-1", job_id="job-1", annotation_id="ann-1",
            rating="up", created_at="2025-01-01T00:00:00+00:00",
        )
        assert entry.lineage == []

    def test_serialization_roundtrip(self):
        entry = FeedbackEntry(
            id="fb-1",
            job_id="job-1",
            annotation_id="ann-1",
            rating="up",
            lineage=[{"stage": "resolution", "action": "enriched", "detail": "test"}],
            created_at="2025-01-01T00:00:00+00:00",
        )
        data = entry.model_dump()
        restored = FeedbackEntry(**data)
        assert restored == entry
        assert len(restored.lineage) == 1


class TestInsightsSummaryModel:
    def test_default_insights(self):
        summary = InsightsSummary()
        assert summary.total_feedback == 0
        assert summary.thumbs_up == 0
        assert summary.thumbs_down == 0
        assert summary.by_stage == {}
        assert summary.most_downvoted_concepts == []
        assert summary.recent_feedback == []


class TestFeedbackStore:
    @pytest.fixture
    def store(self, tmp_path: Path) -> FeedbackStore:
        return FeedbackStore(base_dir=tmp_path / "feedback")

    @pytest.mark.asyncio
    async def test_save_and_load(self, store: FeedbackStore):
        entry = FeedbackEntry(
            id="fb-1",
            job_id="job-1",
            annotation_id="ann-1",
            rating="up",
            created_at="2025-01-01T00:00:00+00:00",
        )
        await store.save(entry)
        loaded = await store.load("fb-1")
        assert loaded is not None
        assert loaded.id == "fb-1"
        assert loaded.rating == "up"

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, store: FeedbackStore):
        loaded = await store.load("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_list_all(self, store: FeedbackStore):
        for i in range(3):
            await store.save(FeedbackEntry(
                id=f"fb-{i}",
                job_id="job-1",
                annotation_id=f"ann-{i}",
                rating="up" if i % 2 == 0 else "down",
                created_at=f"2025-01-0{i + 1}T00:00:00+00:00",
            ))
        entries = await store.list_all()
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_list_by_job(self, store: FeedbackStore):
        await store.save(FeedbackEntry(
            id="fb-1", job_id="job-1", annotation_id="ann-1",
            rating="up", created_at="2025-01-01T00:00:00+00:00",
        ))
        await store.save(FeedbackEntry(
            id="fb-2", job_id="job-2", annotation_id="ann-2",
            rating="down", created_at="2025-01-02T00:00:00+00:00",
        ))
        entries = await store.list_by_job("job-1")
        assert len(entries) == 1
        assert entries[0].job_id == "job-1"

    @pytest.mark.asyncio
    async def test_get_insights(self, store: FeedbackStore):
        await store.save(FeedbackEntry(
            id="fb-1", job_id="job-1", annotation_id="ann-1",
            rating="up", stage="entity_ruler",
            created_at="2025-01-01T00:00:00+00:00",
        ))
        await store.save(FeedbackEntry(
            id="fb-2", job_id="job-1", annotation_id="ann-2",
            rating="down", stage="entity_ruler",
            folio_label="Breach of Contract", folio_iri="http://example.com/breach",
            created_at="2025-01-02T00:00:00+00:00",
        ))
        await store.save(FeedbackEntry(
            id="fb-3", job_id="job-1", annotation_id="ann-3",
            rating="down", stage="reconciliation",
            folio_label="Breach of Contract", folio_iri="http://example.com/breach",
            created_at="2025-01-03T00:00:00+00:00",
        ))

        insights = await store.get_insights()
        assert insights.total_feedback == 3
        assert insights.thumbs_up == 1
        assert insights.thumbs_down == 2
        assert "entity_ruler" in insights.by_stage
        assert insights.by_stage["entity_ruler"]["up"] == 1
        assert insights.by_stage["entity_ruler"]["down"] == 1
        assert insights.by_stage["reconciliation"]["down"] == 1
        assert len(insights.most_downvoted_concepts) >= 1
        assert insights.most_downvoted_concepts[0]["folio_label"] == "Breach of Contract"
        assert insights.most_downvoted_concepts[0]["downvotes"] == 2
        assert len(insights.recent_feedback) == 3

    @pytest.mark.asyncio
    async def test_delete(self, store: FeedbackStore):
        await store.save(FeedbackEntry(
            id="fb-1", job_id="job-1", annotation_id="ann-1",
            rating="up", created_at="2025-01-01T00:00:00+00:00",
        ))
        assert await store.delete("fb-1") is True
        assert await store.load("fb-1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store: FeedbackStore):
        assert await store.delete("nonexistent") is False

    @pytest.mark.asyncio
    async def test_delete_all(self, store: FeedbackStore):
        for i in range(3):
            await store.save(FeedbackEntry(
                id=f"fb-{i}", job_id="job-1", annotation_id=f"ann-{i}",
                rating="up", created_at=f"2025-01-0{i+1}T00:00:00+00:00",
            ))
        count = await store.delete_all()
        assert count == 3
        assert await store.list_all() == []

    @pytest.mark.asyncio
    async def test_save_and_load_with_lineage(self, store: FeedbackStore):
        entry = FeedbackEntry(
            id="fb-lin", job_id="job-1", annotation_id="ann-1",
            rating="down",
            lineage=[
                {"stage": "entity_ruler", "action": "created", "detail": "Matched 'Tort'"},
                {"stage": "reconciliation", "action": "rejected", "detail": "Filtered out"},
            ],
            created_at="2025-01-01T00:00:00+00:00",
        )
        await store.save(entry)
        loaded = await store.load("fb-lin")
        assert loaded is not None
        assert len(loaded.lineage) == 2
        assert loaded.lineage[0]["stage"] == "entity_ruler"
        assert loaded.lineage[1]["action"] == "rejected"

    @pytest.mark.asyncio
    async def test_get_insights_by_job(self, store: FeedbackStore):
        await store.save(FeedbackEntry(
            id="fb-1", job_id="job-1", annotation_id="ann-1",
            rating="up", created_at="2025-01-01T00:00:00+00:00",
        ))
        await store.save(FeedbackEntry(
            id="fb-2", job_id="job-2", annotation_id="ann-2",
            rating="down", created_at="2025-01-02T00:00:00+00:00",
        ))

        insights = await store.get_insights(job_id="job-1")
        assert insights.total_feedback == 1
        assert insights.thumbs_up == 1
        assert insights.thumbs_down == 0


class TestFeedbackAPI:
    @pytest.fixture
    def client(self, tmp_path: Path):
        """Create a test client with isolated storage."""
        import app.api.routes.feedback as fb_mod
        import app.api.routes.enrich as enrich_mod

        fb_mod._feedback_store = FeedbackStore(base_dir=tmp_path / "feedback")
        fb_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")

        from app.main import app
        return TestClient(app)

    @pytest.fixture
    def job_with_annotation(self, client, tmp_path: Path):
        """Create a completed job with an annotation that has lineage."""
        import app.api.routes.feedback as fb_mod

        ann = Annotation(
            id="ann-123",
            span=Span(start=0, end=18, text="Breach of Contract"),
            concepts=[ConceptMatch(
                concept_text="Breach of Contract",
                folio_iri="http://example.com/breach",
                folio_label="Breach of Contract",
                confidence=0.95,
                source="entity_ruler",
            )],
            state="confirmed",
            lineage=[
                StageEvent(stage="entity_ruler", action="created",
                           detail="Matched preferred label 'Breach of Contract' (multi-word)",
                           confidence=0.95),
                StageEvent(stage="reconciliation", action="confirmed",
                           detail="Both EntityRuler and LLM agree"),
                StageEvent(stage="string_matching", action="confirmed",
                           detail="Aho-Corasick span match, enriched with FOLIO data"),
            ],
        )
        job = Job(
            input=DocumentInput(content="Breach of Contract case"),
            status=JobStatus.COMPLETED,
        )
        job.result.annotations = [ann]

        # Save directly via store
        loop = asyncio.get_event_loop()
        loop.run_until_complete(fb_mod._job_store.save(job))
        return job

    def test_submit_feedback(self, client, job_with_annotation):
        job = job_with_annotation
        resp = client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "down",
            "comment": "Wrong concept",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "saved"
        assert "id" in data

    def test_submit_feedback_invalid_rating(self, client, job_with_annotation):
        job = job_with_annotation
        resp = client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "maybe",
        })
        assert resp.status_code == 422

    def test_submit_feedback_job_not_found(self, client):
        resp = client.post("/feedback", json={
            "job_id": str(uuid4()),
            "annotation_id": "ann-123",
            "rating": "up",
        })
        assert resp.status_code == 404

    def test_submit_feedback_annotation_not_found(self, client, job_with_annotation):
        job = job_with_annotation
        resp = client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "nonexistent",
            "rating": "up",
        })
        assert resp.status_code == 404

    def test_get_insights_empty(self, client):
        resp = client.get("/feedback/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_feedback"] == 0

    def test_get_insights_after_feedback(self, client, job_with_annotation):
        job = job_with_annotation
        client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "down",
            "stage": "entity_ruler",
        })
        resp = client.get("/feedback/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_feedback"] == 1
        assert data["thumbs_down"] == 1

    def test_get_job_insights(self, client, job_with_annotation):
        job = job_with_annotation
        client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "up",
        })
        resp = client.get(f"/feedback/insights/{job.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_feedback"] == 1

    def test_feedback_captures_lineage_snapshot(self, client, job_with_annotation):
        """Submitting feedback should snapshot the annotation's lineage trail."""
        job = job_with_annotation
        resp = client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "down",
            "comment": "Wrong concept",
        })
        assert resp.status_code == 201
        feedback_id = resp.json()["id"]

        # Check the persisted entry has lineage
        import app.api.routes.feedback as fb_mod
        loop = asyncio.get_event_loop()
        entry = loop.run_until_complete(fb_mod._feedback_store.load(feedback_id))
        assert entry is not None
        assert len(entry.lineage) == 3
        assert entry.lineage[0]["stage"] == "entity_ruler"
        assert entry.lineage[1]["stage"] == "reconciliation"
        assert entry.lineage[2]["stage"] == "string_matching"
        assert entry.annotation_text == "Breach of Contract"
        assert entry.folio_label == "Breach of Contract"

    def test_export_json(self, client, job_with_annotation):
        job = job_with_annotation
        client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "down",
        })
        resp = client.get("/feedback/export?format=json")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        import json
        data = json.loads(resp.content)
        assert len(data) == 1
        assert data[0]["rating"] == "down"
        assert len(data[0]["lineage"]) == 3

    def test_export_csv(self, client, job_with_annotation):
        job = job_with_annotation
        client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "up",
        })
        resp = client.get("/feedback/export?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert "rating" in lines[0]
        assert "lineage" in lines[0]

    def test_delete_single_feedback(self, client, job_with_annotation):
        job = job_with_annotation
        resp = client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "down",
        })
        feedback_id = resp.json()["id"]

        resp = client.delete(f"/feedback/{feedback_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1

        # Verify it's gone
        resp = client.get("/feedback/insights")
        assert resp.json()["total_feedback"] == 0

    def test_delete_nonexistent_feedback(self, client):
        resp = client.delete("/feedback/nonexistent-id")
        assert resp.status_code == 404

    def test_upsert_same_annotation(self, client, job_with_annotation):
        """Second feedback on same annotation updates, not duplicates."""
        job = job_with_annotation
        client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "up",
        })
        client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "down",
        })

        resp = client.get("/feedback/insights")
        data = resp.json()
        assert data["total_feedback"] == 1
        assert data["thumbs_down"] == 1  # Updated to latest rating

    def test_clear_all_feedback(self, client, job_with_annotation):
        job = job_with_annotation
        client.post("/feedback", json={
            "job_id": str(job.id),
            "annotation_id": "ann-123",
            "rating": "up",
        })

        resp = client.delete("/feedback")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1

        # Verify all gone
        resp = client.get("/feedback/insights")
        assert resp.json()["total_feedback"] == 0


class TestLineageAPI:
    @pytest.fixture
    def client(self, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")

        from app.main import app
        return TestClient(app)

    def test_get_annotation_lineage(self, client, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        from app.models.annotation import StageEvent

        ann = Annotation(
            id="ann-456",
            span=Span(start=0, end=5, text="hello"),
            lineage=[
                StageEvent(stage="entity_ruler", action="created", detail="test"),
                StageEvent(stage="reconciliation", action="confirmed"),
            ],
        )
        job = Job(
            input=DocumentInput(content="hello world"),
            status=JobStatus.COMPLETED,
        )
        job.result.annotations = [ann]

        loop = asyncio.get_event_loop()
        loop.run_until_complete(enrich_mod._job_store.save(job))

        resp = client.get(f"/enrich/{job.id}/annotations/ann-456/lineage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["annotation_id"] == "ann-456"
        assert len(data["lineage"]) == 2
        assert data["lineage"][0]["stage"] == "entity_ruler"
        assert data["lineage"][1]["stage"] == "reconciliation"

    def test_get_lineage_job_not_found(self, client):
        resp = client.get(f"/enrich/{uuid4()}/annotations/ann-1/lineage")
        assert resp.status_code == 404

    def test_get_lineage_annotation_not_found(self, client, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod

        job = Job(
            input=DocumentInput(content="test"),
            status=JobStatus.COMPLETED,
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(enrich_mod._job_store.save(job))

        resp = client.get(f"/enrich/{job.id}/annotations/nonexistent/lineage")
        assert resp.status_code == 404
