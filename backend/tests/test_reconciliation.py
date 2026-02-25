import pytest

from app.models.annotation import ConceptMatch
from app.services.reconciliation.reconciler import Reconciler


def _concept(text: str, source: str = "llm", confidence: float = 0.9, branches: list[str] | None = None) -> ConceptMatch:
    return ConceptMatch(concept_text=text, source=source, confidence=confidence, branches=branches or [])


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
        because confidence=0.72 is above the threshold."""
        reconciler = Reconciler()
        ruler = [_concept("court", source="entity_ruler", confidence=0.72)]
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


class TestMultiBranchReconciliation:
    """Tests for multi-branch support: same text, different IRIs."""

    def test_same_text_different_iri_both_survive(self):
        """Two concepts with the same text but different IRIs should both be reconciled."""
        reconciler = Reconciler()
        ruler = [
            ConceptMatch(concept_text="Bankruptcy", source="entity_ruler",
                         confidence=0.72, folio_iri="iri_area_of_law",
                         branches=["Area of Law"]),
            ConceptMatch(concept_text="Bankruptcy", source="entity_ruler",
                         confidence=0.72, folio_iri="iri_service",
                         branches=["Service"]),
        ]
        llm = []
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 2
        iris = {r.concept.folio_iri for r in results}
        assert "iri_area_of_law" in iris
        assert "iri_service" in iris

    def test_same_text_same_iri_deduplicated(self):
        """Two concepts with the same text and same IRI should be deduplicated."""
        reconciler = Reconciler()
        ruler = [
            ConceptMatch(concept_text="Contract", source="entity_ruler",
                         confidence=0.72, folio_iri="iri1"),
            ConceptMatch(concept_text="Contract", source="entity_ruler",
                         confidence=0.80, folio_iri="iri1"),
        ]
        llm = []
        results = reconciler.reconcile(ruler, llm)
        # Same (text, IRI) → dict keying picks one (the last one wins in dict)
        assert len(results) == 1
        assert results[0].concept.folio_iri == "iri1"

    def test_multi_branch_ruler_and_llm_agree(self):
        """Multi-branch: ruler and LLM agree on one IRI, ruler-only on another."""
        reconciler = Reconciler()
        ruler = [
            ConceptMatch(concept_text="Bankruptcy", source="entity_ruler",
                         confidence=0.72, folio_iri="iri_aol",
                         branches=["Area of Law"]),
            ConceptMatch(concept_text="Bankruptcy", source="entity_ruler",
                         confidence=0.72, folio_iri="iri_svc",
                         branches=["Service"]),
        ]
        llm = [
            ConceptMatch(concept_text="Bankruptcy", source="llm",
                         confidence=0.85, folio_iri="iri_aol",
                         branches=["Area of Law"]),
        ]
        results = reconciler.reconcile(ruler, llm)
        assert len(results) == 2
        cats = {r.concept.folio_iri: r.category for r in results}
        assert cats["iri_aol"] == "both_agree"
        assert cats["iri_svc"] == "ruler_only"


class TestIRIPreservation:
    """Tests for IRI-preservation logic in embedding triage reconciliation."""

    def test_ruler_iri_preserved_when_llm_has_none(self):
        """When ruler has an IRI but LLM doesn't, ruler's IRI should be preserved."""
        from unittest.mock import MagicMock
        mock_emb = MagicMock()
        mock_emb.index_size = 100
        reconciler = Reconciler(embedding_service=mock_emb)

        ruler = [ConceptMatch(concept_text="cause of action", source="entity_ruler",
                              confidence=0.90, folio_iri="iri_correct", folio_label="Cause of Action")]
        llm = [ConceptMatch(concept_text="cause of action", source="llm",
                            confidence=0.85, folio_iri=None, folio_label=None)]
        results = reconciler.reconcile_with_embedding_triage(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "both_agree"
        assert results[0].concept.folio_iri == "iri_correct"
        # Diminishing boost: base=0.90, boost=0.05*(1-0.90)=0.005
        assert abs(results[0].concept.confidence - 0.905) < 1e-9

    def test_llm_used_when_neither_has_iri(self):
        """When neither side has an IRI, LLM version should be used (existing behavior)."""
        from unittest.mock import MagicMock
        mock_emb = MagicMock()
        mock_emb.index_size = 100
        reconciler = Reconciler(embedding_service=mock_emb)

        ruler = [ConceptMatch(concept_text="due process", source="entity_ruler",
                              confidence=0.80, folio_iri=None)]
        llm = [ConceptMatch(concept_text="due process", source="llm",
                            confidence=0.85, folio_iri=None)]
        results = reconciler.reconcile_with_embedding_triage(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "both_agree"
        assert results[0].concept.source == "reconciled"
        # LLM version used — diminishing boost: base=0.85, boost=0.05*(1-0.85)=0.0075
        assert abs(results[0].concept.confidence - 0.8575) < 1e-9

    def test_llm_iri_used_when_ruler_has_none(self):
        """When LLM has an IRI but ruler doesn't, LLM version should be used."""
        from unittest.mock import MagicMock
        mock_emb = MagicMock()
        mock_emb.index_size = 100
        reconciler = Reconciler(embedding_service=mock_emb)

        ruler = [ConceptMatch(concept_text="injunction", source="entity_ruler",
                              confidence=0.80, folio_iri=None)]
        llm = [ConceptMatch(concept_text="injunction", source="llm",
                            confidence=0.85, folio_iri="iri_llm", folio_label="Injunction")]
        results = reconciler.reconcile_with_embedding_triage(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "both_agree"
        assert results[0].concept.folio_iri == "iri_llm"


class TestEmbeddingTriage:
    def test_embedding_triage_without_service_falls_back(self):
        """Without embedding service, triage delegates to basic reconciliation."""
        reconciler = Reconciler(embedding_service=None)
        ruler = [_concept("court", source="entity_ruler", confidence=0.80)]
        llm = [_concept("court", source="llm", confidence=0.85)]
        results = reconciler.reconcile_with_embedding_triage(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "both_agree"

    def test_embedding_triage_same_iri_agrees(self):
        """When both paths map to the same IRI, treat as agreement."""
        from unittest.mock import MagicMock
        mock_emb = MagicMock()
        mock_emb.index_size = 100
        reconciler = Reconciler(embedding_service=mock_emb)

        ruler = [ConceptMatch(concept_text="court", source="entity_ruler",
                              confidence=0.90, folio_iri="iri1")]
        llm = [ConceptMatch(concept_text="court", source="llm",
                            confidence=0.85, folio_iri="iri1")]
        results = reconciler.reconcile_with_embedding_triage(ruler, llm)
        assert len(results) == 1
        assert results[0].category == "both_agree"

    def test_embedding_triage_conflict_resolves(self):
        """When IRIs differ, embedding similarity should resolve the conflict."""
        from unittest.mock import MagicMock
        mock_emb = MagicMock()
        mock_emb.index_size = 100
        # similarity_batch receives [("court","Court"), ("court","Justice")]
        mock_emb.similarity_batch.return_value = [0.90, 0.50]
        reconciler = Reconciler(embedding_service=mock_emb)

        ruler = [ConceptMatch(concept_text="court", source="entity_ruler",
                              confidence=0.90, folio_iri="iri1", folio_label="Court")]
        llm = [ConceptMatch(concept_text="court", source="llm",
                            confidence=0.85, folio_iri="iri2", folio_label="Justice")]
        results = reconciler.reconcile_with_embedding_triage(ruler, llm)
        assert len(results) >= 1
        assert results[0].category == "conflict_resolved"
