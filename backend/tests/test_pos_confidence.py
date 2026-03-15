"""Tests for POS-powered confidence modulation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.annotation import (
    Annotation,
    ConceptMatch,
    PropertyAnnotation,
    Span,
)
from app.services.nlp.pos_lookup import (
    get_fine_tags_for_span,
    get_majority_pos,
    get_pos_for_span,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sentence_pos(
    text: str,
    tokens: list[str],
    pos_tags: list[str],
    fine_tags: list[str] | None = None,
    start: int = 0,
) -> dict:
    """Build a sentence_pos dict mimicking SentencePOS.model_dump()."""
    return {
        "sentence_index": 0,
        "start": start,
        "end": start + len(text),
        "text": text,
        "tokens": tokens,
        "pos_tags": pos_tags,
        "fine_tags": fine_tags or [""] * len(tokens),
        "dep_labels": [""] * len(tokens),
        "head_indices": list(range(len(tokens))),
    }


def _make_concept_job(
    ann_text: str,
    ann_start: int,
    pos_tag: str,
    match_type: str = "alternative",
    confidence: float = 0.60,
    state: str = "confirmed",
) -> tuple[MagicMock, Annotation]:
    """Create a minimal Job-like object with one concept annotation."""
    job = MagicMock()
    ann = Annotation(
        span=Span(start=ann_start, end=ann_start + len(ann_text), text=ann_text),
        concepts=[ConceptMatch(
            concept_text=ann_text,
            confidence=confidence,
            match_type=match_type,
            source="entity_ruler",
        )],
        state=state,
    )
    job.result.annotations = [ann]
    sent = _make_sentence_pos(
        f"The {ann_text} was issued",
        ["The", ann_text, "was", "issued"],
        ["DET", pos_tag, "AUX", "VERB"],
        start=0,
    )
    job.result.metadata = {"sentence_pos": [sent]}
    return job, ann


def _make_property_job(
    prop_text: str,
    pos_tag: str,
    source: str = "aho_corasick",
    confidence: float = 0.70,
) -> tuple[MagicMock, PropertyAnnotation]:
    """Create a minimal Job-like object with one property annotation."""
    job = MagicMock()
    prop = PropertyAnnotation(
        property_text=prop_text,
        folio_label=prop_text,
        span=Span(start=4, end=4 + len(prop_text), text=prop_text),
        confidence=confidence,
        source=source,
    )
    sent = _make_sentence_pos(
        f"The {prop_text} was important",
        ["The", prop_text, "was", "important"],
        ["DET", pos_tag, "AUX", "ADJ"],
        start=0,
    )
    job.result.metadata = {"sentence_pos": [sent]}
    return job, prop


# ---------------------------------------------------------------------------
# POS Lookup Utility Tests
# ---------------------------------------------------------------------------

class TestGetPosForSpan:
    def test_single_token(self):
        sent = _make_sentence_pos(
            "The court granted the motion",
            ["The", "court", "granted", "the", "motion"],
            ["DET", "NOUN", "VERB", "DET", "NOUN"],
            start=0,
        )
        # "granted" starts at index 10
        assert get_pos_for_span(10, 17, [sent]) == ["VERB"]

    def test_multi_token(self):
        sent = _make_sentence_pos(
            "legal contract was signed",
            ["legal", "contract", "was", "signed"],
            ["ADJ", "NOUN", "AUX", "VERB"],
            start=0,
        )
        # "legal contract" = 0..14
        assert get_pos_for_span(0, 14, [sent]) == ["ADJ", "NOUN"]

    def test_span_outside_sentences(self):
        sent = _make_sentence_pos("hello world", ["hello", "world"], ["NOUN", "NOUN"], start=0)
        assert get_pos_for_span(100, 110, [sent]) == []

    def test_empty_sentence_pos(self):
        assert get_pos_for_span(0, 5, []) == []


class TestGetMajorityPos:
    def test_returns_most_frequent(self):
        sent = _make_sentence_pos(
            "the big red ball",
            ["the", "big", "red", "ball"],
            ["DET", "ADJ", "ADJ", "NOUN"],
            start=0,
        )
        # "big red ball" = 4..16, pos = ADJ, ADJ, NOUN → majority = ADJ
        assert get_majority_pos(4, 16, [sent]) == "ADJ"

    def test_single_token_returns_that_pos(self):
        sent = _make_sentence_pos("grant", ["grant"], ["VERB"], start=0)
        assert get_majority_pos(0, 5, [sent]) == "VERB"

    def test_no_data_returns_none(self):
        assert get_majority_pos(0, 5, []) is None


class TestGetFineTagsForSpan:
    def test_returns_fine_tags(self):
        sent = _make_sentence_pos(
            "The court granted the motion",
            ["The", "court", "granted", "the", "motion"],
            ["DET", "NOUN", "VERB", "DET", "NOUN"],
            fine_tags=["DT", "NN", "VBD", "DT", "NN"],
            start=0,
        )
        assert get_fine_tags_for_span(10, 17, [sent]) == ["VBD"]


# ---------------------------------------------------------------------------
# Concept POS Penalty Tests (ReconciliationStage)
# ---------------------------------------------------------------------------

class TestConceptPosPenalty:
    def test_verb_concept_penalized(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("grant", 4, "VERB")
        boosted, penalized = ReconciliationStage._apply_pos_adjustments(job)
        assert penalized == 1
        assert boosted == 0
        assert ann.concepts[0].confidence < 0.60

    def test_noun_concept_not_penalized(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        # NOUN gets boosted instead of penalized, so confidence should increase
        job, ann = _make_concept_job("grant", 4, "NOUN")
        boosted, penalized = ReconciliationStage._apply_pos_adjustments(job)
        assert penalized == 0
        assert boosted == 1
        assert ann.concepts[0].confidence > 0.60

    def test_multi_word_not_adjusted(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job = MagicMock()
        ann = Annotation(
            span=Span(start=4, end=16, text="legal motion"),
            concepts=[ConceptMatch(
                concept_text="legal motion",
                confidence=0.60,
                match_type="alternative",
                source="entity_ruler",
            )],
            state="confirmed",
        )
        job.result.annotations = [ann]
        sent = _make_sentence_pos(
            "The legal motion was filed",
            ["The", "legal", "motion", "was", "filed"],
            ["DET", "ADJ", "NOUN", "AUX", "VERB"],
            start=0,
        )
        job.result.metadata = {"sentence_pos": [sent]}
        boosted, penalized = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 0
        assert penalized == 0

    def test_penalty_below_threshold_rejects(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("grant", 4, "VERB", confidence=0.18)
        ReconciliationStage._apply_pos_adjustments(job)
        assert ann.state == "rejected"

    def test_pos_disabled_no_change(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("grant", 4, "VERB")
        with patch("app.config.settings") as mock_settings:
            mock_settings.pos_confidence_enabled = False
            mock_settings.pos_tagging_enabled = True
            boosted, penalized = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 0
        assert penalized == 0
        assert ann.concepts[0].confidence == 0.60


# ---------------------------------------------------------------------------
# Concept POS Boost Tests (ReconciliationStage)
# ---------------------------------------------------------------------------

class TestConceptPosBoost:
    def test_noun_span_boosts_class_concept(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("obligation", 4, "NOUN", confidence=0.60)
        boosted, penalized = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 1
        assert penalized == 0
        # NOUN × 1.0 × 0.10 = +0.10
        assert ann.concepts[0].confidence == pytest.approx(0.70)

    def test_propn_span_boosts_stronger(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("Congress", 4, "PROPN", confidence=0.60)
        boosted, _ = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 1
        # PROPN × 1.2 × 0.10 = +0.12
        assert ann.concepts[0].confidence == pytest.approx(0.72)

    def test_adj_span_boosts_mild(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("contractual", 4, "ADJ", confidence=0.60)
        boosted, _ = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 1
        # ADJ × 0.6 × 0.10 = +0.06
        assert ann.concepts[0].confidence == pytest.approx(0.66)

    def test_boost_applies_to_preferred_label(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("obligation", 4, "NOUN", match_type="preferred", confidence=0.72)
        boosted, _ = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 1
        assert ann.concepts[0].confidence == pytest.approx(0.82)

    def test_boost_clamped_at_1_0(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("obligation", 4, "PROPN", confidence=0.95)
        boosted, _ = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 1
        # 0.95 + 0.12 would be 1.07, clamped to 1.0
        assert ann.concepts[0].confidence == 1.0

    def test_boost_skips_multiword_spans(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job = MagicMock()
        ann = Annotation(
            span=Span(start=0, end=16, text="legal obligation"),
            concepts=[ConceptMatch(
                concept_text="legal obligation",
                confidence=0.60,
                source="entity_ruler",
            )],
            state="confirmed",
        )
        job.result.annotations = [ann]
        sent = _make_sentence_pos(
            "legal obligation was clear",
            ["legal", "obligation", "was", "clear"],
            ["ADJ", "NOUN", "AUX", "ADJ"],
            start=0,
        )
        job.result.metadata = {"sentence_pos": [sent]}
        boosted, _ = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 0
        assert ann.concepts[0].confidence == 0.60

    def test_boost_disabled_when_pos_confidence_off(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("obligation", 4, "NOUN", confidence=0.60)
        with patch("app.config.settings") as mock_settings:
            mock_settings.pos_confidence_enabled = False
            mock_settings.pos_tagging_enabled = True
            boosted, penalized = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 0
        assert penalized == 0
        assert ann.concepts[0].confidence == 0.60

    def test_boost_zero_config_disables(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("obligation", 4, "NOUN", confidence=0.60)
        with patch("app.config.settings") as mock_settings:
            mock_settings.pos_confidence_enabled = True
            mock_settings.pos_tagging_enabled = True
            mock_settings.pos_concept_match_boost = 0.0
            mock_settings.pos_concept_mismatch_penalty = 0.15
            boosted, penalized = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 0
        assert ann.concepts[0].confidence == 0.60

    def test_no_double_boost_penalty(self):
        """Same span gets boost OR penalty, never both — POS tags are mutually exclusive."""
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        # NOUN should get boost, not penalty
        job, ann = _make_concept_job("grant", 4, "NOUN", match_type="alternative", confidence=0.60)
        boosted, penalized = ReconciliationStage._apply_pos_adjustments(job)
        assert boosted == 1
        assert penalized == 0
        assert ann.concepts[0].confidence > 0.60

    def test_lineage_records_boost_event(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("obligation", 4, "NOUN", confidence=0.60)
        ReconciliationStage._apply_pos_adjustments(job)
        boost_events = [e for e in ann.lineage if e.action == "pos_boosted"]
        assert len(boost_events) == 1
        assert "POS agreement: NOUN" in boost_events[0].detail
        assert boost_events[0].confidence == pytest.approx(0.70)


# ---------------------------------------------------------------------------
# Concept POS Metadata Sync Tests
# ---------------------------------------------------------------------------

class TestConceptPosMetadataSync:
    def test_pos_adjustment_propagates_to_reconciled_concepts(self):
        from app.pipeline.stages.reconciliation_stage import ReconciliationStage

        job, ann = _make_concept_job("obligation", 4, "NOUN", confidence=0.60)
        # Add reconciled_concepts metadata dict to simulate real pipeline
        job.result.metadata["reconciled_concepts"] = [
            {"concept_text": "obligation", "folio_iri": "", "confidence": 0.60},
        ]
        ReconciliationStage._apply_pos_adjustments(job)
        ReconciliationStage._sync_pos_to_metadata(job)
        # Metadata dict should be updated to match the boosted annotation
        assert job.result.metadata["reconciled_concepts"][0]["confidence"] == pytest.approx(0.70)


# ---------------------------------------------------------------------------
# Branch POS Affinity Tests (BranchJudgeStage)
# ---------------------------------------------------------------------------

class TestBranchPosAffinity:
    def test_verb_action_branch_boost(self):
        from app.pipeline.stages.branch_judge_stage import BranchJudgeStage

        affinity = BranchJudgeStage._pos_branch_affinity("VERB", "Legal Process")
        assert affinity > 0

    def test_noun_entity_branch_boost(self):
        from app.pipeline.stages.branch_judge_stage import BranchJudgeStage

        affinity = BranchJudgeStage._pos_branch_affinity("NOUN", "Legal Document")
        assert affinity > 0

    def test_mismatch_penalty(self):
        from app.pipeline.stages.branch_judge_stage import BranchJudgeStage

        affinity = BranchJudgeStage._pos_branch_affinity("VERB", "Legal Document")
        assert affinity < 0


# ---------------------------------------------------------------------------
# Property POS Penalty Tests (LLMPropertyStage)
# ---------------------------------------------------------------------------

class TestPropertyPosPenalty:
    def test_noun_property_penalized(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("filing", "NOUN")
        boosted, penalized = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert penalized == 1
        assert boosted == 0
        assert prop.confidence < 0.70

    def test_verb_property_not_penalized(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        # VERB gets boosted instead of penalized
        job, prop = _make_property_job("filing", "VERB")
        boosted, penalized = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert penalized == 0
        assert boosted == 1
        assert prop.confidence > 0.70

    def test_llm_property_skipped(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("filing", "NOUN", source="llm")
        boosted, penalized = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert boosted == 0
        assert penalized == 0


# ---------------------------------------------------------------------------
# Property POS Boost Tests (LLMPropertyStage)
# ---------------------------------------------------------------------------

class TestPropertyPosBoost:
    def test_verb_span_boosts_property(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("governs", "VERB", confidence=0.70)
        boosted, penalized = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert boosted == 1
        assert penalized == 0
        # VERB × 1.0 × 0.10 = +0.10
        assert prop.confidence == pytest.approx(0.80)

    def test_aux_span_boosts_property(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("has", "AUX", confidence=0.70)
        boosted, _ = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert boosted == 1
        # AUX × 0.8 × 0.10 = +0.08
        assert prop.confidence == pytest.approx(0.78)

    def test_property_boost_skips_llm_sourced(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("governs", "VERB", source="llm", confidence=0.70)
        boosted, _ = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert boosted == 0
        assert prop.confidence == 0.70

    def test_property_boost_clamped_at_1_0(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("governs", "VERB", confidence=0.95)
        boosted, _ = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert boosted == 1
        assert prop.confidence == 1.0

    def test_property_boost_disabled_when_off(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("governs", "VERB", confidence=0.70)
        with patch("app.config.settings") as mock_settings:
            mock_settings.pos_confidence_enabled = False
            mock_settings.pos_tagging_enabled = True
            boosted, penalized = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert boosted == 0
        assert penalized == 0
        assert prop.confidence == 0.70

    def test_property_lineage_records_boost(self):
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("governs", "VERB", confidence=0.70)
        LLMPropertyStage._apply_pos_adjustments(job, [prop])
        boost_events = [e for e in prop.lineage if e.action == "pos_boosted"]
        assert len(boost_events) == 1
        assert "POS agreement: VERB" in boost_events[0].detail

    def test_existing_property_penalty_still_works(self):
        """Regression: NOUN Aho-Corasick property still penalized -0.12."""
        from app.pipeline.stages.property_stage import LLMPropertyStage

        job, prop = _make_property_job("filing", "NOUN", confidence=0.70)
        _, penalized = LLMPropertyStage._apply_pos_adjustments(job, [prop])
        assert penalized == 1
        assert prop.confidence == pytest.approx(0.58)


# ---------------------------------------------------------------------------
# Triple Confidence Tests (DependencyParser)
# ---------------------------------------------------------------------------

class TestTripleConfidence:
    def _mock_token(self, pos: str):
        tok = MagicMock()
        tok.pos_ = pos
        return tok

    def test_ideal_triple_high_confidence(self):
        from app.services.dependency.parser import DependencyParser

        parser = DependencyParser()
        conf = parser._compute_triple_confidence(
            self._mock_token("PROPN"),
            self._mock_token("VERB"),
            self._mock_token("NOUN"),
            is_passive=False,
        )
        assert conf == pytest.approx(0.80)

    def test_weak_triple_low_confidence(self):
        from app.services.dependency.parser import DependencyParser

        parser = DependencyParser()
        conf = parser._compute_triple_confidence(
            self._mock_token("ADJ"),
            self._mock_token("AUX"),
            self._mock_token("DET"),
            is_passive=False,
        )
        # base 0.50 + 0.10 (AUX counts) = 0.60
        assert conf == pytest.approx(0.60)

    def test_passive_penalty(self):
        from app.services.dependency.parser import DependencyParser

        parser = DependencyParser()
        active = parser._compute_triple_confidence(
            self._mock_token("NOUN"),
            self._mock_token("VERB"),
            self._mock_token("NOUN"),
            is_passive=False,
        )
        passive = parser._compute_triple_confidence(
            self._mock_token("NOUN"),
            self._mock_token("VERB"),
            self._mock_token("NOUN"),
            is_passive=True,
        )
        assert passive < active
        assert active - passive == pytest.approx(0.05)
