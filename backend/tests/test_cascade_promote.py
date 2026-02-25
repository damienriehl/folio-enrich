"""Tests for selective cascade-promote endpoint."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.job import Job, JobStatus
from app.models.document import DocumentInput
from app.storage.job_store import JobStore


class TestCascadePromote:
    @pytest.fixture
    def client(self, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod
        enrich_mod._job_store = JobStore(base_dir=tmp_path / "jobs")
        from app.main import app
        return TestClient(app)

    def _make_ann(self, ann_id, text, primary_iri, backup_iri=None):
        concepts = [ConceptMatch(
            concept_text=text, folio_iri=primary_iri,
            folio_label=text, confidence=0.9, source="entity_ruler",
        )]
        if backup_iri:
            concepts.append(ConceptMatch(
                concept_text=text, folio_iri=backup_iri,
                folio_label=text + " (alt)", confidence=0.7, source="llm",
            ))
        return Annotation(
            id=ann_id,
            span=Span(start=0, end=len(text), text=text),
            concepts=concepts,
        )

    @pytest.fixture
    def job_with_shared_iris(self, client, tmp_path: Path):
        import app.api.routes.enrich as enrich_mod

        old_iri = "http://example.com/old"
        new_iri = "http://example.com/new"
        job = Job(
            input=DocumentInput(content="test document"),
            status=JobStatus.COMPLETED,
        )
        job.result.annotations = [
            self._make_ann("ann-1", "contract", old_iri, new_iri),
            self._make_ann("ann-2", "agreement", old_iri, new_iri),
            self._make_ann("ann-3", "deal", old_iri, new_iri),
            self._make_ann("ann-4", "unrelated", "http://example.com/other"),
        ]
        loop = asyncio.get_event_loop()
        loop.run_until_complete(enrich_mod._job_store.save(job))
        return job, old_iri, new_iri

    def test_cascade_all_when_no_ids(self, client, job_with_shared_iris):
        job, old_iri, new_iri = job_with_shared_iris
        resp = client.post(f"/enrich/{job.id}/cascade-promote", json={
            "old_iri": old_iri, "new_iri": new_iri,
        })
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 3

    def test_cascade_selective_ids(self, client, job_with_shared_iris):
        job, old_iri, new_iri = job_with_shared_iris
        resp = client.post(f"/enrich/{job.id}/cascade-promote", json={
            "old_iri": old_iri, "new_iri": new_iri,
            "annotation_ids": ["ann-1", "ann-3"],
        })
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 2

    def test_cascade_selective_skips_unchecked(self, client, job_with_shared_iris):
        """Only ann-2 is selected; ann-1 and ann-3 should keep old primary."""
        job, old_iri, new_iri = job_with_shared_iris
        resp = client.post(f"/enrich/{job.id}/cascade-promote", json={
            "old_iri": old_iri, "new_iri": new_iri,
            "annotation_ids": ["ann-2"],
        })
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 1

        # Verify ann-1 still has old primary
        job_resp = client.get(f"/enrich/{job.id}")
        anns = {a["id"]: a for a in job_resp.json()["result"]["annotations"]}
        assert anns["ann-1"]["concepts"][0]["folio_iri"] == old_iri
        assert anns["ann-2"]["concepts"][0]["folio_iri"] == new_iri
        assert anns["ann-3"]["concepts"][0]["folio_iri"] == old_iri

    def test_cascade_empty_ids_updates_none(self, client, job_with_shared_iris):
        job, old_iri, new_iri = job_with_shared_iris
        resp = client.post(f"/enrich/{job.id}/cascade-promote", json={
            "old_iri": old_iri, "new_iri": new_iri,
            "annotation_ids": [],
        })
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 0
