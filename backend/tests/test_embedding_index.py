"""Tests for FOLIO embedding indexing."""

import pytest

from app.services.embedding.service import EmbeddingService


class TestEmbeddingService:
    def test_index_labels(self):
        svc = EmbeddingService()
        labels = ["breach of contract", "motion to dismiss", "court order"]
        metadata = [
            {"iri": "iri1", "label": "Breach of Contract", "type": "preferred"},
            {"iri": "iri2", "label": "Motion to Dismiss", "type": "preferred"},
            {"iri": "iri3", "label": "Court Order", "type": "preferred"},
        ]
        svc.index_labels(labels, metadata)
        assert svc.index_size == 3

    def test_search_returns_results(self):
        svc = EmbeddingService()
        labels = ["breach of contract", "motion to dismiss", "court order"]
        metadata = [
            {"iri": "iri1", "label": "Breach of Contract", "type": "preferred"},
            {"iri": "iri2", "label": "Motion to Dismiss", "type": "preferred"},
            {"iri": "iri3", "label": "Court Order", "type": "preferred"},
        ]
        svc.index_labels(labels, metadata)
        results = svc.search("contract violation", top_k=1)
        assert len(results) == 1
        assert results[0].score > 0

    def test_search_empty_index(self):
        svc = EmbeddingService()
        results = svc.search("anything")
        assert results == []

    def test_similarity(self):
        svc = EmbeddingService()
        svc.index_labels(["test"])  # Force model load
        score = svc.similarity("breach of contract", "contract breach")
        assert score > 0.5

    def test_index_folio_labels_with_mock(self):
        """Test index_folio_labels with a mock folio service."""
        from unittest.mock import MagicMock
        from app.services.folio.folio_service import FOLIOConcept, LabelInfo

        mock_folio = MagicMock()
        mock_folio.get_all_labels.return_value = {
            "court": LabelInfo(
                concept=FOLIOConcept(
                    iri="iri1", preferred_label="Court",
                    alternative_labels=[], definition="", branch="", parent_iris=[],
                ),
                label_type="preferred",
                matched_label="Court",
            ),
        }

        svc = EmbeddingService()
        svc.index_folio_labels(mock_folio)
        assert svc.index_size == 1
        mock_folio.get_all_labels.assert_called_once()
