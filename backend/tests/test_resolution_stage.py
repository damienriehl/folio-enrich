"""Tests for ResolutionStage embedding context scoring."""

from unittest.mock import MagicMock

from app.pipeline.stages.resolution_stage import ResolutionStage


class TestApplyEmbeddingContextScores:
    def _make_stage(self, similarity_value=0.8, index_size=100):
        mock_emb = MagicMock()
        mock_emb.index_size = index_size
        mock_emb.similarity.return_value = similarity_value
        return ResolutionStage(embedding_service=mock_emb), mock_emb

    def test_blends_60_40(self):
        stage, mock_emb = self._make_stage(similarity_value=0.6)
        concepts = [{
            "concept_text": "breach of contract",
            "folio_definition": "Failure to perform contractual obligations",
            "confidence": 0.80,
        }]
        stage._apply_embedding_context_scores(concepts, "The breach of contract was clear.")
        # 0.80 * 0.6 + 0.6 * 0.4 = 0.48 + 0.24 = 0.72
        assert abs(concepts[0]["confidence"] - 0.72) < 1e-4

    def test_records_lineage_event(self):
        stage, _ = self._make_stage(similarity_value=0.7)
        concepts = [{
            "concept_text": "damages",
            "folio_definition": "Monetary compensation",
            "confidence": 0.90,
        }]
        stage._apply_embedding_context_scores(concepts, "The damages were substantial.")
        events = concepts[0].get("_lineage_events", [])
        assert len(events) == 1
        assert events[0]["stage"] == "resolution"
        assert events[0]["action"] == "embedding_context"

    def test_skips_when_no_embedding_service(self):
        stage = ResolutionStage(embedding_service=None)
        concepts = [{"concept_text": "test", "folio_definition": "def", "confidence": 0.80}]
        stage._apply_embedding_context_scores(concepts, "Some text about test.")
        assert concepts[0]["confidence"] == 0.80

    def test_skips_when_index_empty(self):
        stage, _ = self._make_stage(index_size=0)
        concepts = [{"concept_text": "test", "folio_definition": "def", "confidence": 0.80}]
        stage._apply_embedding_context_scores(concepts, "Some text about test.")
        assert concepts[0]["confidence"] == 0.80

    def test_skips_when_no_definition(self):
        stage, mock_emb = self._make_stage()
        concepts = [{"concept_text": "test", "folio_definition": "", "confidence": 0.80}]
        stage._apply_embedding_context_scores(concepts, "Some text about test.")
        assert concepts[0]["confidence"] == 0.80
        mock_emb.similarity.assert_not_called()

    def test_handles_similarity_exception(self):
        stage, mock_emb = self._make_stage()
        mock_emb.similarity.side_effect = Exception("embedding error")
        concepts = [{"concept_text": "test", "folio_definition": "def", "confidence": 0.80}]
        stage._apply_embedding_context_scores(concepts, "Some text about test.")
        # Confidence unchanged on exception
        assert concepts[0]["confidence"] == 0.80

    def test_falls_back_to_concept_text_when_not_in_document(self):
        stage, mock_emb = self._make_stage(similarity_value=0.5)
        concepts = [{
            "concept_text": "habeas corpus",
            "folio_definition": "A writ requiring a person to be brought before a judge",
            "confidence": 0.90,
        }]
        # Concept text not in the document
        stage._apply_embedding_context_scores(concepts, "This document is about something else entirely.")
        # similarity called with concept_text as sentence fallback
        mock_emb.similarity.assert_called_once()
        call_args = mock_emb.similarity.call_args[0]
        assert call_args[0] == "habeas corpus"  # fell back to concept_text

    def test_clamps_similarity_above_1(self):
        stage, mock_emb = self._make_stage(similarity_value=1.5)
        concepts = [{"concept_text": "test", "folio_definition": "def", "confidence": 0.80}]
        stage._apply_embedding_context_scores(concepts, "test context.")
        # Clamped to 1.0: 0.80 * 0.6 + 1.0 * 0.4 = 0.88
        assert abs(concepts[0]["confidence"] - 0.88) < 1e-4
