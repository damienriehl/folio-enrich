"""Tests for annotation dismiss/restore endpoints."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.job import Job, JobStatus
from app.models.document import DocumentInput
from app.storage.job_store import JobStore


class TestDismissRestore:
    @pytest.fixture
    def client(self, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
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


class TestBulkReject:
    @pytest.fixture
    def client(self, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
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


class TestExportExcludesDismissed:
    @pytest.fixture
    def client(self, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        import app.api.routes.export as export_mod
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
        export_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
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
