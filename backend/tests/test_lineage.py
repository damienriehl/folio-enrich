"""Tests for stage lineage tracking on annotations."""

import pytest

from app.models.annotation import (
    Annotation,
    ConceptMatch,
    FeedbackItem,
    Span,
    StageEvent,
)
from app.pipeline.stages.base import record_lineage


class TestStageEventModel:
    def test_create_stage_event(self):
        evt = StageEvent(stage="entity_ruler", action="created", detail="test")
        assert evt.stage == "entity_ruler"
        assert evt.action == "created"
        assert evt.detail == "test"
        assert evt.confidence is None
        assert evt.timestamp == ""

    def test_stage_event_with_confidence(self):
        evt = StageEvent(stage="resolution", action="enriched", confidence=0.95)
        assert evt.confidence == 0.95

    def test_stage_event_serialization_roundtrip(self):
        evt = StageEvent(
            stage="reconciliation",
            action="confirmed",
            detail="Both agree",
            confidence=0.9,
            timestamp="2025-01-01T00:00:00+00:00",
        )
        data = evt.model_dump()
        restored = StageEvent(**data)
        assert restored == evt


class TestFeedbackItemModel:
    def test_create_feedback_item(self):
        fb = FeedbackItem(rating="up")
        assert fb.rating == "up"
        assert fb.id  # auto-generated
        assert fb.created_at  # auto-generated
        assert fb.stage is None
        assert fb.comment == ""

    def test_feedback_item_with_stage(self):
        fb = FeedbackItem(rating="down", stage="entity_ruler", comment="Wrong concept")
        assert fb.rating == "down"
        assert fb.stage == "entity_ruler"
        assert fb.comment == "Wrong concept"

    def test_feedback_item_serialization_roundtrip(self):
        fb = FeedbackItem(rating="up", stage="resolution")
        data = fb.model_dump()
        restored = FeedbackItem(**data)
        assert restored.id == fb.id
        assert restored.rating == fb.rating
        assert restored.stage == fb.stage


class TestAnnotationLineage:
    def test_annotation_defaults_to_empty_lineage(self):
        ann = Annotation(span=Span(start=0, end=5, text="hello"))
        assert ann.lineage == []
        assert ann.feedback == []

    def test_annotation_backward_compat_deserialization(self):
        """Existing serialized annotations without lineage/feedback should deserialize."""
        data = {
            "id": "abc",
            "span": {"start": 0, "end": 5, "text": "hello"},
            "concepts": [],
            "state": "preliminary",
        }
        ann = Annotation(**data)
        assert ann.lineage == []
        assert ann.feedback == []

    def test_annotation_with_lineage_serialization(self):
        ann = Annotation(
            span=Span(start=0, end=5, text="hello"),
            lineage=[
                StageEvent(stage="entity_ruler", action="created", detail="test"),
            ],
        )
        data = ann.model_dump()
        assert len(data["lineage"]) == 1
        restored = Annotation(**data)
        assert len(restored.lineage) == 1
        assert restored.lineage[0].stage == "entity_ruler"


class TestRecordLineage:
    def test_record_lineage_appends_event(self):
        ann = Annotation(span=Span(start=0, end=5, text="hello"))
        record_lineage(ann, "entity_ruler", "created", detail="Matched 'hello'", confidence=0.9)
        assert len(ann.lineage) == 1
        assert ann.lineage[0].stage == "entity_ruler"
        assert ann.lineage[0].action == "created"
        assert ann.lineage[0].detail == "Matched 'hello'"
        assert ann.lineage[0].confidence == 0.9
        assert ann.lineage[0].timestamp  # auto-populated

    def test_record_lineage_multiple_events(self):
        ann = Annotation(span=Span(start=0, end=5, text="hello"))
        record_lineage(ann, "entity_ruler", "created")
        record_lineage(ann, "reconciliation", "confirmed")
        record_lineage(ann, "string_matching", "confirmed")
        assert len(ann.lineage) == 3
        assert [e.stage for e in ann.lineage] == [
            "entity_ruler", "reconciliation", "string_matching"
        ]

    def test_record_lineage_default_confidence_is_none(self):
        ann = Annotation(span=Span(start=0, end=5, text="hello"))
        record_lineage(ann, "test", "test")
        assert ann.lineage[0].confidence is None


class TestEntityRulerLineage:
    @pytest.mark.asyncio
    async def test_entity_ruler_populates_lineage(self):
        """EntityRulerStage should populate lineage on created annotations."""
        from app.pipeline.stages.entity_ruler_stage import EntityRulerStage
        from app.services.entity_ruler.ruler import EntityRulerMatch, FOLIOEntityRuler
        from app.models.job import Job
        from app.models.document import DocumentInput, CanonicalText, TextChunk

        stage = EntityRulerStage()
        # Build a minimal job with canonical text
        job = Job(input=DocumentInput(content="Breach of Contract case"))
        text = "Breach of Contract case"
        job.result.canonical_text = CanonicalText(
            full_text=text,
            chunks=[TextChunk(text=text, start_offset=0, end_offset=len(text), chunk_index=0)],
        )

        # Mock ruler to return a match
        class MockRuler:
            def find_matches(self, text):
                return [
                    EntityRulerMatch(
                        text="Breach of Contract",
                        entity_id="http://example.com/breach",
                        start_char=0,
                        end_char=18,
                        label="FOLIO_CONCEPT",
                        match_type="preferred",
                    )
                ]

        stage.ruler = MockRuler()
        stage._patterns_loaded = True

        result = await stage.execute(job)
        annotations = result.result.annotations
        assert len(annotations) >= 1
        ann = annotations[0]
        assert len(ann.lineage) >= 1
        assert ann.lineage[0].stage == "entity_ruler"
        assert ann.lineage[0].action == "created"
        assert "Breach of Contract" in ann.lineage[0].detail


class TestReconciliationLineage:
    @pytest.mark.asyncio
    async def test_reconciliation_adds_lineage_events(self):
        """ReconciliationStage should add lineage events when confirming/rejecting."""
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage
        from app.models.annotation import Annotation, ConceptMatch, Span
        from app.models.job import Job
        from app.models.document import DocumentInput, CanonicalText, TextChunk
        from app.services.reconciliation.reconciler import ReconciliationResult

        # Create a mock reconciler
        class MockReconciler:
            _embedding_service = None

            def reconcile(self, ruler, llm):
                return [
                    ReconciliationResult(
                        concept=ConceptMatch(
                            concept_text="Breach of Contract",
                            folio_iri="http://example.com/breach",
                            confidence=0.95,
                            source="entity_ruler",
                        ),
                        category="both_agree",
                    ),
                ]

        stage = ReconciliationStage(reconciler=MockReconciler())
        job = Job(input=DocumentInput(content="test"))
        job.result.canonical_text = CanonicalText(
            full_text="test",
            chunks=[TextChunk(text="test", start_offset=0, end_offset=4, chunk_index=0)],
        )

        # Add preliminary annotation
        ann = Annotation(
            span=Span(start=0, end=18, text="Breach of Contract"),
            concepts=[ConceptMatch(
                concept_text="Breach of Contract",
                folio_iri="http://example.com/breach",
                confidence=0.95,
                source="entity_ruler",
            )],
            state="preliminary",
        )
        job.result.annotations = [ann]
        job.result.metadata["ruler_concepts"] = [
            ConceptMatch(
                concept_text="Breach of Contract",
                folio_iri="http://example.com/breach",
                confidence=0.95,
                source="entity_ruler",
            ).model_dump()
        ]

        result = await stage.execute(job)
        ann = result.result.annotations[0]
        assert ann.state == "confirmed"
        # Should have a reconciliation lineage event
        recon_events = [e for e in ann.lineage if e.stage == "reconciliation"]
        assert len(recon_events) == 1
        assert recon_events[0].action == "confirmed"
        assert "Both EntityRuler and LLM agree" in recon_events[0].detail
