import pytest

from app.models.annotation import ConceptMatch
from app.services.reconciliation.reconciler import Reconciler


def _concept(text: str, source: str = "llm", confidence: float = 0.9, branch: str = "") -> ConceptMatch:
    return ConceptMatch(concept_text=text, source=source, confidence=confidence, branch=branch)


class TestReconciler:
    def test_both_agree(self):
        reconciler = Reconciler()
        ruler = [_concept("breach of contract", source="entity_ruler", confidence=1.0)]
        llm = [_concept("breach of contract", source="llm", confidence=0.9)]
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "both_agree"
        assert results[0].concept.source == "reconciled"
        assert results[0].concept.confidence >= 1.0

    def test_ruler_only_multiword(self):
        reconciler = Reconciler()
        ruler = [_concept("motion to dismiss", source="entity_ruler", confidence=1.0)]
        llm = []
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "ruler_only"

    def test_ruler_only_single_word_low_confidence_dropped(self):
        reconciler = Reconciler()
        ruler = [_concept("the", source="entity_ruler", confidence=0.5)]
        llm = []
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 0

    def test_ruler_only_alt_label_single_word_dropped(self):
        """Single-word alternative label matches (e.g., 'grant' → Donation) should be
        filtered out because confidence=0.35 is below the threshold."""
        reconciler = Reconciler()
        ruler = [_concept("grant", source="entity_ruler", confidence=0.35)]
        llm = []
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 0

    def test_ruler_only_preferred_label_single_word_kept(self):
        """Single-word preferred label matches (e.g., 'court') should be kept
        because confidence=0.80 is above the threshold."""
        reconciler = Reconciler()
        ruler = [_concept("court", source="entity_ruler", confidence=0.80)]
        llm = []
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "ruler_only"

    def test_llm_only(self):
        reconciler = Reconciler()
        ruler = []
        llm = [_concept("contextual concept", source="llm", confidence=0.85)]
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "llm_only"
        assert results[0].concept.source == "llm"

    def test_mixed_results(self):
        reconciler = Reconciler()
        ruler = [
            _concept("breach of contract", source="entity_ruler", confidence=1.0),
            _concept("court", source="entity_ruler", confidence=1.0),
        ]
        llm = [
            _concept("breach of contract", source="llm", confidence=0.9),
            _concept("damages", source="llm", confidence=0.88),
        ]
        results = reconciler.reconcile(ruler, llm)
        categories = {r.category for r in results}
        assert "both_agree" in categories  # breach of contract
        assert "ruler_only" in categories or any(r.concept.concept_text.lower() == "court" for r in results)
        assert "llm_only" in categories  # damages

    def test_case_insensitive_matching(self):
        reconciler = Reconciler()
        ruler = [_concept("Court", source="entity_ruler")]
        llm = [_concept("court", source="llm")]
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "both_agree"
