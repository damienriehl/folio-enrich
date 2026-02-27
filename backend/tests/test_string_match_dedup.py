"""Tests for StringMatchStage._dedup_overlapping_same_iri."""

from __future__ import annotations

from app.models.annotation import Annotation, ConceptMatch, Span, StageEvent
from app.pipeline.stages.string_match_stage import StringMatchStage


def _make_ann(
    start: int,
    end: int,
    iri: str,
    confidence: float = 0.80,
    state: str = "confirmed",
    lineage: list[StageEvent] | None = None,
) -> Annotation:
    return Annotation(
        span=Span(start=start, end=end, text=f"text[{start}:{end}]"),
        concepts=[ConceptMatch(
            concept_text=f"concept-{iri}",
            folio_iri=iri,
            folio_label=f"Label {iri}",
            confidence=confidence,
            state="confirmed",
        )],
        state=state,
        lineage=lineage or [],
    )


class TestDedupOverlappingSameIri:
    def test_identical_span_same_iri_keeps_highest_confidence(self):
        """Two annotations at the exact same span with the same IRI: keep higher confidence."""
        a1 = _make_ann(10, 30, "iri:1", confidence=0.80)
        a2 = _make_ann(10, 30, "iri:1", confidence=0.84)
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert len(result) == 1
        assert result[0].concepts[0].confidence == 0.84

    def test_contained_span_same_iri_keeps_longer(self):
        """Contained span (A inside B) with the same IRI: keep the longer span."""
        a1 = _make_ann(100, 130, "iri:1", confidence=0.80)
        a2 = _make_ann(110, 130, "iri:1", confidence=0.85)
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert len(result) == 1
        assert result[0].span.start == 100
        assert result[0].span.end == 130

    def test_overlapping_different_iris_preserved(self):
        """Two annotations at the same span with different IRIs: both kept (multi-branch)."""
        a1 = _make_ann(10, 30, "iri:1", confidence=0.80)
        a2 = _make_ann(10, 30, "iri:2", confidence=0.90)
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert len(result) == 2
        iris = {r.concepts[0].folio_iri for r in result}
        assert iris == {"iri:1", "iri:2"}

    def test_non_overlapping_same_iri_preserved(self):
        """Two non-overlapping spans with the same IRI: both kept."""
        a1 = _make_ann(10, 30, "iri:1", confidence=0.80)
        a2 = _make_ann(200, 220, "iri:1", confidence=0.85)
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert len(result) == 2

    def test_rejected_bypasses_dedup(self):
        """A rejected annotation at the same span/IRI is not merged."""
        a1 = _make_ann(10, 30, "iri:1", confidence=0.80, state="rejected")
        a2 = _make_ann(10, 30, "iri:1", confidence=0.84, state="confirmed")
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert len(result) == 2

    def test_lineage_merged(self):
        """Winner absorbs loser's lineage events plus a dedup_merged event."""
        evt1 = StageEvent(stage="entity_ruler", action="created", detail="ruler hit")
        evt2 = StageEvent(stage="llm_concept", action="created", detail="llm hit")
        a1 = _make_ann(10, 30, "iri:1", confidence=0.80, lineage=[evt1])
        a2 = _make_ann(10, 30, "iri:1", confidence=0.84, lineage=[evt2])
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert len(result) == 1
        actions = [e.action for e in result[0].lineage]
        assert "dedup_merged" in actions
        # Winner (a2, higher confidence) should have both original events plus the merge event
        stages = [e.stage for e in result[0].lineage]
        assert "llm_concept" in stages  # winner's own event
        assert "entity_ruler" in stages  # absorbed from loser

    def test_three_way_merge(self):
        """Three overlapping annotations for the same IRI: only the longest survives."""
        a1 = _make_ann(100, 140, "iri:1", confidence=0.75)  # longest
        a2 = _make_ann(100, 130, "iri:1", confidence=0.80)
        a3 = _make_ann(110, 130, "iri:1", confidence=0.85)
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2, a3])
        iri1_anns = [r for r in result if r.concepts[0].folio_iri == "iri:1"]
        assert len(iri1_anns) == 1
        assert iri1_anns[0].span.start == 100
        assert iri1_anns[0].span.end == 140
        # Should have two dedup_merged events (one per absorbed annotation)
        dedup_events = [e for e in iri1_anns[0].lineage if e.action == "dedup_merged"]
        assert len(dedup_events) == 2

    def test_partial_overlap_same_iri_keeps_longer(self):
        """Partially overlapping spans (not contained) with same IRI: keep longer."""
        a1 = _make_ann(10, 30, "iri:1", confidence=0.80)
        a2 = _make_ann(20, 45, "iri:1", confidence=0.75)
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert len(result) == 1
        # Longer span is [20,45] (length 25 > 20)
        assert result[0].span.start == 20
        assert result[0].span.end == 45

    def test_no_iri_bypasses_dedup(self):
        """Annotations without an IRI bypass dedup."""
        a1 = _make_ann(10, 30, "", confidence=0.80)
        a1.concepts[0].folio_iri = None
        a2 = _make_ann(10, 30, "", confidence=0.85)
        a2.concepts[0].folio_iri = None
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert len(result) == 2

    def test_result_sorted_by_span_start(self):
        """Output is sorted by span start regardless of input order."""
        a1 = _make_ann(200, 220, "iri:2", confidence=0.80)
        a2 = _make_ann(10, 30, "iri:1", confidence=0.90)
        result = StringMatchStage._dedup_overlapping_same_iri([a1, a2])
        assert result[0].span.start <= result[1].span.start
