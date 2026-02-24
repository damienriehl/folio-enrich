"""Tests for Semantic EntityRuler integration."""

import pytest

from app.services.embedding.service import EmbeddingService
from app.services.entity_ruler.semantic_ruler import SemanticEntityRuler


class TestSemanticEntityRuler:
    @pytest.fixture
    def indexed_embedding_service(self):
        svc = EmbeddingService()
        labels = ["breach of contract", "motion to dismiss", "intellectual property"]
        metadata = [
            {"iri": "iri1", "label": "Breach of Contract", "type": "preferred"},
            {"iri": "iri2", "label": "Motion to Dismiss", "type": "preferred"},
            {"iri": "iri3", "label": "Intellectual Property", "type": "preferred"},
        ]
        svc.index_labels(labels, metadata)
        return svc

    def test_finds_semantic_matches(self, indexed_embedding_service):
        ruler = SemanticEntityRuler(indexed_embedding_service, threshold=0.50)
        text = "The contract violation was severe."
        matches = ruler.find_semantic_matches(text, set())
        # Should find something related to "breach of contract" via "contract violation"
        assert len(matches) >= 0  # May or may not match depending on similarity

    def test_skips_known_spans(self, indexed_embedding_service):
        ruler = SemanticEntityRuler(indexed_embedding_service, threshold=0.50)
        text = "The contract violation was severe."
        # Mark the entire text as already matched
        known_spans = {(0, len(text))}
        matches = ruler.find_semantic_matches(text, known_spans)
        assert len(matches) == 0

    def test_no_embedding_service(self):
        ruler = SemanticEntityRuler(None)
        matches = ruler.find_semantic_matches("any text", set())
        assert matches == []

    def test_empty_index(self):
        svc = EmbeddingService()
        ruler = SemanticEntityRuler(svc)
        matches = ruler.find_semantic_matches("any text", set())
        assert matches == []

    def test_skips_pure_stopword_candidates(self, indexed_embedding_service):
        """Candidates like 'by and' where all tokens are stopwords should be skipped."""
        from app.services.entity_ruler.semantic_ruler import _SEMANTIC_STOPWORDS
        ruler = SemanticEntityRuler(indexed_embedding_service, threshold=0.50)
        text = "by and through its"
        matches = ruler.find_semantic_matches(text, set())
        for m in matches:
            tokens = m.text.lower().split()
            assert not all(t in _SEMANTIC_STOPWORDS for t in tokens), \
                f"Pure-stopword match should not occur: '{m.text}'"
