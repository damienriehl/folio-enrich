"""Tests for annotation dismiss/restore endpoints."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.annotation import Annotation, ConceptMatch, Span, StageEvent
from app.models.job import Job, JobStatus
from app.models.document import DocumentInput
from app.storage.feedback_store import FeedbackStore
from app.storage.job_store import JobStore


class TestDismissRestore:
    @pytest.fixture
    def client(self, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        import app.api.routes.feedback as fb_mod
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
        fb_mod._job_store = enrich_mod._job_store
        fb_mod._feedback_store = FeedbackStore(base_dir=tmp_path / "feedback")
        from app.main import app
        return TestClient(app)

    def _make_ann(self, ann_id, text, iri, state="confirmed"):
        return Annotation(
            id=ann_id,
            span=Span(start=0, end=len(text), text=text),
            concepts=[ConceptMatch(
                concept_text=text, folio_iri=iri,
                folio_label=text, confidence=0.9, source="entity_ruler",
            )],
            state=state,
        )

    @pytest.fixture
    def job_with_annotations(self, client, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod

        iri = "http://example.com/bid"
        job = Job(
            input=DocumentInput(content="Bid document"),
            status=JobStatus.COMPLETED,
        )
        job.result.annotations = [
            self._make_ann("ann-1", "Bid", iri),
            self._make_ann("ann-2", "Bid", iri),
            self._make_ann("ann-3", "Bid", iri),
            self._make_ann("ann-4", "Court", "http://example.com/court"),
        ]
        loop = asyncio.get_event_loop()
        loop.run_until_complete(enrich_mod._job_store.save(job))
        return job, iri

    def test_reject_annotation(self, client, job_with_annotations):
        job, iri = job_with_annotations
        resp = client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["annotation_id"] == "ann-1"
        assert data["same_concept_count"] == 2  # ann-2 and ann-3 still active
        assert data["folio_iri"] == iri

    def test_reject_updates_state(self, client, job_with_annotations):
        job, _ = job_with_annotations
        client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        resp = client.get(f"/enrich/{job.id}")
        anns = {a["id"]: a for a in resp.json()["result"]["annotations"]}
        assert anns["ann-1"]["state"] == "rejected"
        assert anns["ann-1"]["dismissed_at"] is not None

    def test_reject_adds_lineage_event(self, client, job_with_annotations):
        job, _ = job_with_annotations
        client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        resp = client.get(f"/enrich/{job.id}")
        ann = next(a for a in resp.json()["result"]["annotations"] if a["id"] == "ann-1")
        assert any(e["action"] == "user_rejected" for e in ann["lineage"])

    def test_reject_already_rejected(self, client, job_with_annotations):
        job, _ = job_with_annotations
        client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        resp = client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_rejected"

    def test_reject_not_found(self, client, job_with_annotations):
        job, _ = job_with_annotations
        resp = client.post(f"/enrich/{job.id}/annotations/nonexistent/reject")
        assert resp.status_code == 404

    def test_restore_annotation(self, client, job_with_annotations):
        job, _ = job_with_annotations
        client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        resp = client.post(f"/enrich/{job.id}/annotations/ann-1/restore")
        assert resp.status_code == 200
        assert resp.json()["status"] == "restored"

    def test_restore_updates_state(self, client, job_with_annotations):
        job, _ = job_with_annotations
        client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        client.post(f"/enrich/{job.id}/annotations/ann-1/restore")
        resp = client.get(f"/enrich/{job.id}")
        ann = next(a for a in resp.json()["result"]["annotations"] if a["id"] == "ann-1")
        assert ann["state"] == "confirmed"
        assert ann["dismissed_at"] is None

    def test_restore_not_rejected(self, client, job_with_annotations):
        job, _ = job_with_annotations
        resp = client.post(f"/enrich/{job.id}/annotations/ann-1/restore")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_rejected"

    def test_restore_not_found(self, client, job_with_annotations):
        job, _ = job_with_annotations
        resp = client.post(f"/enrich/{job.id}/annotations/nonexistent/restore")
        assert resp.status_code == 404

    def test_reject_creates_feedback_entry(self, client, job_with_annotations):
        job, _ = job_with_annotations
        client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        resp = client.get(f"/feedback/insights/{job.id}")
        data = resp.json()
        assert data["total_dismissed"] == 1
        assert len(data["recent_feedback"]) == 1
        fb = data["recent_feedback"][0]
        assert fb["rating"] == "dismissed"
        assert fb["annotation_text"] == "Bid"
        assert fb["folio_label"] == "Bid"
        assert fb["folio_iri"] == "http://example.com/bid"
        assert len(fb["lineage"]) > 0

    def test_reject_feedback_has_sentence_context(self, client, tmp_path: Path):
        """Reject captures sentence_text when available."""
        import app.api.routes.enrich as enrich_mod
        ann = Annotation(
            id="ann-ctx",
            span=Span(start=10, end=13, text="Bid",
                      sentence_text="The Bid was submitted on time."),
            concepts=[ConceptMatch(
                concept_text="Bid", folio_iri="http://example.com/bid",
                folio_label="Bid", confidence=0.9, source="entity_ruler",
            )],
            state="confirmed",
            lineage=[StageEvent(stage="entity_ruler", action="created", detail="Matched")],
        )
        job = Job(input=DocumentInput(content="The Bid was submitted on time."),
                  status=JobStatus.COMPLETED)
        job.result.annotations = [ann]
        loop = asyncio.get_event_loop()
        loop.run_until_complete(enrich_mod._job_store.save(job))

        client.post(f"/enrich/{job.id}/annotations/ann-ctx/reject")
        resp = client.get(f"/feedback/insights/{job.id}")
        fb = resp.json()["recent_feedback"][0]
        assert fb["sentence_text"] == "The Bid was submitted on time."
        assert fb["annotation_text"] == "Bid"

    def test_restore_removes_feedback_entry(self, client, job_with_annotations):
        job, _ = job_with_annotations
        client.post(f"/enrich/{job.id}/annotations/ann-1/reject")
        # Verify feedback exists
        resp = client.get(f"/feedback/insights/{job.id}")
        assert resp.json()["total_feedback"] == 1

        # Restore
        client.post(f"/enrich/{job.id}/annotations/ann-1/restore")
        resp = client.get(f"/feedback/insights/{job.id}")
        assert resp.json()["total_feedback"] == 0


class TestBulkReject:
    @pytest.fixture
    def client(self, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        import app.api.routes.feedback as fb_mod
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
        fb_mod._job_store = enrich_mod._job_store
        fb_mod._feedback_store = FeedbackStore(base_dir=tmp_path / "feedback")
        from app.main import app
        return TestClient(app)

    @pytest.fixture
    def job_with_shared_concepts(self, client, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod

        iri = "http://example.com/bid"
        job = Job(
            input=DocumentInput(content="Bid document"),
            status=JobStatus.COMPLETED,
        )
        job.result.annotations = [
            Annotation(
                id="ann-1", span=Span(start=0, end=3, text="Bid"),
                concepts=[ConceptMatch(concept_text="Bid", folio_iri=iri, folio_label="Bid", confidence=0.9)],
                state="confirmed",
            ),
            Annotation(
                id="ann-2", span=Span(start=10, end=13, text="Bid"),
                concepts=[ConceptMatch(concept_text="Bid", folio_iri=iri, folio_label="Bid", confidence=0.85)],
                state="confirmed",
            ),
            Annotation(
                id="ann-3", span=Span(start=20, end=25, text="Court"),
                concepts=[ConceptMatch(concept_text="Court", folio_iri="http://example.com/court", folio_label="Court", confidence=0.95)],
                state="confirmed",
            ),
            Annotation(
                id="ann-4", span=Span(start=30, end=33, text="Bid"),
                concepts=[ConceptMatch(concept_text="Bid", folio_iri=iri, folio_label="Bid", confidence=0.8)],
                state="rejected",  # already rejected
            ),
        ]
        loop = asyncio.get_event_loop()
        loop.run_until_complete(enrich_mod._job_store.save(job))
        return job, iri

    def test_bulk_reject(self, client, job_with_shared_concepts):
        job, iri = job_with_shared_concepts
        resp = client.post(f"/enrich/{job.id}/annotations/bulk-reject", json={"folio_iri": iri})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "bulk_rejected"
        assert data["updated_count"] == 2  # ann-1 and ann-2 (ann-4 already rejected)
        assert set(data["rejected_ids"]) == {"ann-1", "ann-2"}

    def test_bulk_reject_skips_already_rejected(self, client, job_with_shared_concepts):
        job, iri = job_with_shared_concepts
        resp = client.post(f"/enrich/{job.id}/annotations/bulk-reject", json={"folio_iri": iri})
        data = resp.json()
        assert "ann-4" not in data["rejected_ids"]

    def test_bulk_reject_no_matches(self, client, job_with_shared_concepts):
        job, _ = job_with_shared_concepts
        resp = client.post(f"/enrich/{job.id}/annotations/bulk-reject", json={"folio_iri": "http://example.com/nonexistent"})
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 0

    def test_bulk_reject_updates_all_states(self, client, job_with_shared_concepts):
        job, iri = job_with_shared_concepts
        client.post(f"/enrich/{job.id}/annotations/bulk-reject", json={"folio_iri": iri})
        resp = client.get(f"/enrich/{job.id}")
        anns = {a["id"]: a for a in resp.json()["result"]["annotations"]}
        assert anns["ann-1"]["state"] == "rejected"
        assert anns["ann-2"]["state"] == "rejected"
        assert anns["ann-3"]["state"] == "confirmed"  # different IRI, untouched
        assert anns["ann-4"]["state"] == "rejected"  # was already rejected

    def test_bulk_reject_job_not_found(self, client):
        from uuid import uuid4
        resp = client.post(f"/enrich/{uuid4()}/annotations/bulk-reject", json={"folio_iri": "http://example.com/x"})
        assert resp.status_code == 404

    def test_bulk_reject_creates_feedback_entries(self, client, job_with_shared_concepts):
        job, iri = job_with_shared_concepts
        client.post(f"/enrich/{job.id}/annotations/bulk-reject", json={"folio_iri": iri})
        resp = client.get(f"/feedback/insights/{job.id}")
        data = resp.json()
        # ann-1 and ann-2 were active with that IRI (ann-4 was already rejected)
        assert data["total_dismissed"] == 2
        assert data["total_feedback"] == 2
        assert all(fb["rating"] == "dismissed" for fb in data["recent_feedback"])
        # Each entry should have context
        for fb in data["recent_feedback"]:
            assert fb["annotation_text"] == "Bid"
            assert fb["folio_iri"] == iri


class TestExportExcludesDismissed:
    @pytest.fixture
    def client(self, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        import app.api.routes.export as export_mod
        import app.api.routes.feedback as fb_mod
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
        export_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
        fb_mod._job_store = enrich_mod._job_store
        fb_mod._feedback_store = FeedbackStore(base_dir=tmp_path / "feedback")
        from app.main import app
        return TestClient(app)

    @pytest.fixture
    def job_with_dismissed(self, client, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod

        job = Job(
            input=DocumentInput(content="Bid in court"),
            status=JobStatus.COMPLETED,
        )
        job.result.annotations = [
            Annotation(
                id="ann-1", span=Span(start=0, end=3, text="Bid"),
                concepts=[ConceptMatch(concept_text="Bid", folio_iri="http://example.com/bid", folio_label="Bid", confidence=0.9)],
                state="rejected",
            ),
            Annotation(
                id="ann-2", span=Span(start=7, end=12, text="court"),
                concepts=[ConceptMatch(concept_text="court", folio_iri="http://example.com/court", folio_label="Court", confidence=0.95)],
                state="confirmed",
            ),
        ]
        loop = asyncio.get_event_loop()
        loop.run_until_complete(enrich_mod._job_store.save(job))
        return job

    def test_export_excludes_rejected_by_default(self, client, job_with_dismissed):
        import json
        job = job_with_dismissed
        resp = client.get(f"/enrich/{job.id}/export?format=json")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data["annotations"]) == 1
        assert data["annotations"][0]["concepts"][0]["folio_label"] == "Court"

    def test_export_includes_rejected_when_requested(self, client, job_with_dismissed):
        import json
        job = job_with_dismissed
        resp = client.get(f"/enrich/{job.id}/export?format=json&include_dismissed=true")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data["annotations"]) == 2
