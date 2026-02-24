"""Tests for progressive rendering pipeline: parallel execution, annotation state
transitions, merge logic, and SSE ID-based tracking."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.document import CanonicalText, DocumentFormat, DocumentInput, TextChunk
from app.models.job import Job, JobResult, JobStatus
from app.pipeline.orchestrator import PipelineOrchestrator, build_pipeline_config
from app.pipeline.stages.base import PipelineStage
from app.pipeline.stages.entity_ruler_stage import EntityRulerStage
from app.pipeline.stages.reconciliation_stage import ReconciliationStage
from app.pipeline.stages.string_match_stage import StringMatchStage
from app.services.entity_ruler.ruler import EntityRulerMatch
from app.services.streaming.sse import job_event_stream
from app.storage.job_store import JobStore


def _make_canonical(text: str) -> CanonicalText:
    """Helper to create a CanonicalText with a single chunk."""
    return CanonicalText(
        full_text=text,
        chunks=[TextChunk(text=text, start_offset=0, end_offset=len(text), chunk_index=0)],
    )


# ── Annotation model ──────────────────────────────────────────────


class TestAnnotationModel:
    def test_annotation_has_id(self):
        ann = Annotation(span=Span(start=0, end=5, text="hello"), concepts=[])
        assert ann.id  # non-empty string
        assert isinstance(ann.id, str)

    def test_annotation_has_state(self):
        ann = Annotation(span=Span(start=0, end=5, text="hello"), concepts=[])
        assert ann.state == "preliminary"

    def test_annotation_unique_ids(self):
        a1 = Annotation(span=Span(start=0, end=5, text="hello"), concepts=[])
        a2 = Annotation(span=Span(start=0, end=5, text="hello"), concepts=[])
        assert a1.id != a2.id

    def test_annotation_state_serialization(self):
        ann = Annotation(span=Span(start=0, end=5, text="hello"), state="confirmed")
        data = ann.model_dump()
        assert data["state"] == "confirmed"
        assert "id" in data


# ── JobStatus ─────────────────────────────────────────────────────


class TestJobStatus:
    def test_enriching_status_exists(self):
        assert JobStatus.ENRICHING.value == "enriching"

    def test_enriching_between_normalizing_and_identifying(self):
        values = [s.value for s in JobStatus]
        norm_idx = values.index("normalizing")
        enrich_idx = values.index("enriching")
        ident_idx = values.index("identifying")
        assert norm_idx < enrich_idx < ident_idx


# ── EntityRulerStage creates preliminary annotations ──────────────


class TestEntityRulerAnnotations:
    @pytest.mark.asyncio
    async def test_creates_preliminary_annotations(self):
        """EntityRulerStage should create Annotation objects with state='preliminary'."""
        # Create a mock ruler that returns known matches
        mock_ruler = MagicMock()
        mock_ruler.find_matches.return_value = [
            EntityRulerMatch(
                text="breach of contract",
                start_char=4,
                end_char=22,
                label="FOLIO_CONCEPT",
                entity_id="https://lmss.sali.org/R1234",
                match_type="preferred",
            ),
        ]

        stage = EntityRulerStage(ruler=mock_ruler)
        stage._patterns_loaded = True  # skip FOLIO loading

        job = Job()
        job.result.canonical_text = _make_canonical("The breach of contract was clear.")

        result = await stage.execute(job)

        assert len(result.result.annotations) == 1
        ann = result.result.annotations[0]
        assert ann.state == "preliminary"
        assert ann.span.start == 4
        assert ann.span.end == 22
        assert ann.span.text == "breach of contract"
        assert ann.concepts[0].source == "entity_ruler"
        assert ann.id  # has a valid id

    @pytest.mark.asyncio
    async def test_resolves_overlapping_spans(self):
        """Overlapping spans should keep the longer match."""
        mock_ruler = MagicMock()
        mock_ruler.find_matches.return_value = [
            EntityRulerMatch(
                text="breach of contract",
                start_char=4,
                end_char=22,
                label="FOLIO_CONCEPT",
                entity_id="https://lmss.sali.org/R1234",
                match_type="preferred",
            ),
            EntityRulerMatch(
                text="contract",
                start_char=14,
                end_char=22,
                label="FOLIO_CONCEPT",
                entity_id="https://lmss.sali.org/R5678",
                match_type="preferred",
            ),
        ]

        stage = EntityRulerStage(ruler=mock_ruler)
        stage._patterns_loaded = True

        job = Job()
        job.result.canonical_text = _make_canonical("The breach of contract was clear.")

        result = await stage.execute(job)

        # Only the longer "breach of contract" should survive
        assert len(result.result.annotations) == 1
        assert result.result.annotations[0].span.text == "breach of contract"


# ── ReconciliationStage updates annotation states ─────────────────


class TestReconciliationAnnotationStates:
    @pytest.mark.asyncio
    async def test_confirmed_when_both_agree(self):
        """Annotations with category 'both_agree' should become confirmed."""
        job = Job()
        job.result.annotations = [
            Annotation(
                span=Span(start=0, end=8, text="contract"),
                concepts=[ConceptMatch(concept_text="contract", source="entity_ruler")],
                state="preliminary",
            ),
        ]
        job.result.metadata["ruler_concepts"] = [
            ConceptMatch(concept_text="contract", source="entity_ruler", confidence=0.9).model_dump()
        ]
        job.result.metadata["llm_concepts"] = {
            "chunk_0": [ConceptMatch(concept_text="contract", source="llm", confidence=0.85).model_dump()]
        }

        # Mock the reconciler to return both_agree
        from app.services.reconciliation.reconciler import ReconciliationResult
        mock_reconciler = MagicMock()
        mock_reconciler.reconcile.return_value = [
            ReconciliationResult(
                concept=ConceptMatch(concept_text="contract", source="reconciled", confidence=0.9),
                category="both_agree",
            )
        ]
        mock_reconciler._embedding_service = None

        stage = ReconciliationStage(reconciler=mock_reconciler)
        result = await stage.execute(job)

        assert result.result.annotations[0].state == "confirmed"

    @pytest.mark.asyncio
    async def test_rejected_when_not_in_reconciled(self):
        """Annotations not in reconciled set should become rejected."""
        job = Job()
        job.result.annotations = [
            Annotation(
                span=Span(start=0, end=5, text="grant"),
                concepts=[ConceptMatch(concept_text="grant", source="entity_ruler", confidence=0.35)],
                state="preliminary",
            ),
        ]
        job.result.metadata["ruler_concepts"] = [
            ConceptMatch(concept_text="grant", source="entity_ruler", confidence=0.35).model_dump()
        ]
        job.result.metadata["llm_concepts"] = {}

        mock_reconciler = MagicMock()
        mock_reconciler.reconcile.return_value = []  # "grant" was filtered out
        mock_reconciler._embedding_service = None

        stage = ReconciliationStage(reconciler=mock_reconciler)
        result = await stage.execute(job)

        assert result.result.annotations[0].state == "rejected"


# ── StringMatchStage merge logic ──────────────────────────────────


class TestStringMatchMerge:
    @pytest.mark.asyncio
    async def test_merges_existing_annotations(self):
        """StringMatchStage should update existing annotations instead of replacing."""
        job = Job()
        text = "The breach of contract was clear."
        job.result.canonical_text = _make_canonical(text)

        # Simulate preliminary annotation from EntityRuler
        existing_ann = Annotation(
            span=Span(start=4, end=22, text="breach of contract"),
            concepts=[ConceptMatch(
                concept_text="breach of contract",
                folio_iri="https://lmss.sali.org/R1234",
                source="entity_ruler",
                confidence=0.95,
            )],
            state="preliminary",
        )
        original_id = existing_ann.id
        job.result.annotations = [existing_ann]

        # Set up resolved concepts for Aho-Corasick
        job.result.metadata["resolved_concepts"] = [
            {
                "concept_text": "breach of contract",
                "folio_iri": "https://lmss.sali.org/R1234",
                "folio_label": "Breach of Contract",
                "folio_definition": "A violation of a contractual obligation.",
                "branches": ["Objectives"],
                "confidence": 0.95,
                "source": "reconciled",
            }
        ]

        stage = StringMatchStage()
        result = await stage.execute(job)

        # Should have merged, preserving the original annotation's id
        matching = [a for a in result.result.annotations if a.span.start == 4 and a.span.end == 22]
        assert len(matching) == 1
        assert matching[0].id == original_id
        assert matching[0].state == "confirmed"
        assert matching[0].concepts[0].folio_label == "Breach of Contract"

    @pytest.mark.asyncio
    async def test_keeps_rejected_annotations(self):
        """Rejected annotations should be preserved in final output."""
        job = Job()
        text = "The grant and contract were reviewed."
        job.result.canonical_text = _make_canonical(text)

        rejected = Annotation(
            span=Span(start=4, end=9, text="grant"),
            concepts=[ConceptMatch(concept_text="grant", source="entity_ruler", confidence=0.35)],
            state="rejected",
        )
        confirmed = Annotation(
            span=Span(start=14, end=22, text="contract"),
            concepts=[ConceptMatch(concept_text="contract", source="entity_ruler", confidence=0.8)],
            state="preliminary",
        )
        job.result.annotations = [rejected, confirmed]

        job.result.metadata["resolved_concepts"] = [
            {
                "concept_text": "contract",
                "folio_iri": "https://lmss.sali.org/R5678",
                "folio_label": "Contract",
                "branches": ["Document / Artifact"],
                "confidence": 0.8,
                "source": "reconciled",
            }
        ]

        stage = StringMatchStage()
        result = await stage.execute(job)

        states = {a.span.text: a.state for a in result.result.annotations}
        assert states["grant"] == "rejected"
        assert states["contract"] == "confirmed"


# ── SSE ID-based tracking ────────────────────────────────────────


class TestSSETracking:
    @pytest.mark.asyncio
    async def test_emits_preliminary_then_update(self, tmp_path: Path):
        """SSE should emit preliminary_annotation first, then annotation_update on state change."""
        store = JobStore(base_dir=tmp_path / "jobs")

        # Create initial job with preliminary annotations
        job = Job()
        job.status = JobStatus.ENRICHING
        ann = Annotation(
            id="test-ann-1",
            span=Span(start=0, end=5, text="hello"),
            concepts=[ConceptMatch(concept_text="hello", source="entity_ruler")],
            state="preliminary",
        )
        job.result.annotations = [ann]
        await store.save(job)

        events = []

        async def collect_events():
            gen = job_event_stream(job.id, store, poll_interval=0.05)
            async for event in gen:
                events.append(event)

        # Start collecting events in background
        task = asyncio.create_task(collect_events())

        # Wait a bit for the initial events to be emitted
        await asyncio.sleep(0.15)

        # Now update the job: change annotation state and mark completed
        job.result.annotations[0].state = "confirmed"
        job.status = JobStatus.COMPLETED
        await store.save(job)

        # Wait for the generator to finish (hits terminal state)
        await asyncio.wait_for(task, timeout=2.0)

        event_types = [e["event"] for e in events]
        assert "status" in event_types
        assert "preliminary_annotation" in event_types
        assert "annotation_update" in event_types
        assert "complete" in event_types


# ── Parallel orchestrator ─────────────────────────────────────────


class TestParallelOrchestrator:
    @pytest.mark.asyncio
    async def test_parallel_pipeline_completes(self, tmp_path: Path):
        """Pipeline with parallel config should complete successfully."""
        store = JobStore(base_dir=tmp_path / "jobs")
        pipeline = PipelineOrchestrator(store)
        job = Job(input=DocumentInput(content="The court granted the motion."))
        result = await pipeline.run(job)

        assert result.status == JobStatus.COMPLETED
        assert result.result.canonical_text is not None

    @pytest.mark.asyncio
    async def test_flat_pipeline_backward_compat(self, tmp_path: Path):
        """Legacy flat stages= path should still work."""

        class DummyStage(PipelineStage):
            @property
            def name(self) -> str:
                return "dummy"

            async def execute(self, job: Job) -> Job:
                job.result.metadata["dummy"] = True
                return job

        store = JobStore(base_dir=tmp_path / "jobs")
        pipeline = PipelineOrchestrator(store, stages=[DummyStage()])
        job = Job()
        result = await pipeline.run(job)

        assert result.status == JobStatus.COMPLETED
        assert result.result.metadata.get("dummy") is True

    @pytest.mark.asyncio
    async def test_enriching_status_set_during_parallel(self, tmp_path: Path):
        """Job should pass through ENRICHING status during parallel phase."""
        store = JobStore(base_dir=tmp_path / "jobs")
        statuses_seen = []

        original_save = store.save

        async def tracking_save(job):
            statuses_seen.append(job.status)
            return await original_save(job)

        store.save = tracking_save

        pipeline = PipelineOrchestrator(store)
        job = Job(input=DocumentInput(content="Test content."))
        await pipeline.run(job)

        assert JobStatus.ENRICHING in statuses_seen


# ── PipelineConfig ────────────────────────────────────────────────


class TestPipelineConfig:
    def test_build_pipeline_config_no_llm(self):
        config = build_pipeline_config(llm=None)
        assert len(config.pre_parallel) == 2
        assert config.entity_ruler is not None
        assert config.llm_concept is None
        assert len(config.post_parallel) >= 3  # reconciliation, resolution, string_match, dependency

    def test_build_pipeline_config_with_llm(self):
        mock_llm = MagicMock()
        config = build_pipeline_config(llm=mock_llm)
        assert config.llm_concept is not None
        # Should have branch_judge and metadata stages too
        stage_names = [s.name for s in config.post_parallel]
        assert "branch_judge" in stage_names
        assert "metadata" in stage_names
