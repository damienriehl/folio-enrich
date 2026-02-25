"""Tests for the ContextualRerankStage."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.job import Job, JobResult, JobStatus
from app.models.document import CanonicalText, TextChunk
from app.pipeline.stages.rerank_stage import ContextualRerankStage


def _make_job(resolved_concepts: list[dict], full_text: str = "Test legal document.") -> Job:
    job = Job(
        id=uuid.uuid4(),
        status=JobStatus.RESOLVING,
        result=JobResult(
            metadata={"resolved_concepts": resolved_concepts},
            canonical_text=CanonicalText(
                full_text=full_text,
                chunks=[TextChunk(
                    text=full_text, start_offset=0,
                    end_offset=len(full_text), chunk_index=0,
                )],
            ),
        ),
    )
    return job


def _make_llm(response: str) -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


class TestContextualRerankStage:
    def test_name(self):
        llm = _make_llm("")
        stage = ContextualRerankStage(llm)
        assert stage.name == "contextual_rerank"

    @pytest.mark.asyncio
    async def test_blends_scores_50_50(self):
        concepts = [
            {
                "concept_text": "breach of contract",
                "folio_iri": "iri1",
                "folio_label": "Breach of Contract",
                "folio_definition": "Failure to perform",
                "confidence": 0.80,
            },
        ]
        llm_response = json.dumps({
            "scores": [
                {
                    "concept_text": "breach of contract",
                    "folio_iri": "iri1",
                    "contextual_score": 0.60,
                    "reasoning": "relevant",
                }
            ]
        })
        llm = _make_llm(llm_response)
        stage = ContextualRerankStage(llm)
        job = _make_job(concepts)

        result = await stage.execute(job)

        # 0.80 * 0.5 + 0.60 * 0.5 = 0.70
        assert abs(result.result.metadata["resolved_concepts"][0]["confidence"] - 0.70) < 1e-4

    @pytest.mark.asyncio
    async def test_records_lineage_event(self):
        concepts = [
            {
                "concept_text": "damages",
                "folio_iri": "iri2",
                "folio_label": "Damages",
                "folio_definition": "Monetary compensation",
                "confidence": 0.90,
            },
        ]
        llm_response = json.dumps({
            "scores": [
                {
                    "concept_text": "damages",
                    "folio_iri": "iri2",
                    "contextual_score": 0.80,
                    "reasoning": "clearly relevant",
                }
            ]
        })
        llm = _make_llm(llm_response)
        stage = ContextualRerankStage(llm)
        job = _make_job(concepts)

        result = await stage.execute(job)

        events = result.result.metadata["resolved_concepts"][0].get("_lineage_events", [])
        assert len(events) == 1
        assert events[0]["stage"] == "contextual_rerank"
        assert events[0]["action"] == "reranked"

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        concepts = [
            {"concept_text": "test", "folio_iri": "iri", "confidence": 0.80},
        ]
        llm = _make_llm("")
        stage = ContextualRerankStage(llm)
        job = _make_job(concepts)

        with patch("app.config.settings") as mock_settings:
            mock_settings.contextual_rerank_enabled = False
            result = await stage.execute(job)

        # Confidence unchanged
        assert result.result.metadata["resolved_concepts"][0]["confidence"] == 0.80
        llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(self):
        concepts = [
            {"concept_text": "court", "folio_iri": "iri3", "confidence": 0.75},
        ]
        llm = _make_llm("")
        llm.complete = AsyncMock(side_effect=Exception("LLM unavailable"))
        stage = ContextualRerankStage(llm)
        job = _make_job(concepts)

        result = await stage.execute(job)

        # Confidence unchanged on failure
        assert result.result.metadata["resolved_concepts"][0]["confidence"] == 0.75

    @pytest.mark.asyncio
    async def test_handles_malformed_json(self):
        concepts = [
            {"concept_text": "court", "folio_iri": "iri3", "confidence": 0.75},
        ]
        llm = _make_llm("This is not valid JSON at all")
        stage = ContextualRerankStage(llm)
        job = _make_job(concepts)

        result = await stage.execute(job)

        # Confidence unchanged when parsing fails
        assert result.result.metadata["resolved_concepts"][0]["confidence"] == 0.75

    @pytest.mark.asyncio
    async def test_skips_when_no_resolved_concepts(self):
        llm = _make_llm("")
        stage = ContextualRerankStage(llm)
        job = _make_job([])

        result = await stage.execute(job)

        llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_concepts_scored(self):
        concepts = [
            {"concept_text": "breach", "folio_iri": "iri1", "confidence": 0.80},
            {"concept_text": "damages", "folio_iri": "iri2", "confidence": 0.70},
        ]
        llm_response = json.dumps({
            "scores": [
                {"concept_text": "breach", "folio_iri": "iri1", "contextual_score": 0.90},
                {"concept_text": "damages", "folio_iri": "iri2", "contextual_score": 0.40},
            ]
        })
        llm = _make_llm(llm_response)
        stage = ContextualRerankStage(llm)
        job = _make_job(concepts, "The breach caused significant damages to the plaintiff.")

        result = await stage.execute(job)

        resolved = result.result.metadata["resolved_concepts"]
        # breach: 0.80*0.5 + 0.90*0.5 = 0.85
        assert abs(resolved[0]["confidence"] - 0.85) < 1e-4
        # damages: 0.70*0.5 + 0.40*0.5 = 0.55
        assert abs(resolved[1]["confidence"] - 0.55) < 1e-4


class TestParseScores:
    def test_parses_valid_json(self):
        raw = json.dumps({
            "scores": [
                {"concept_text": "Test", "folio_iri": "iri1", "contextual_score": 0.85}
            ]
        })
        result = ContextualRerankStage._parse_scores(raw)
        assert ("test", "iri1") in result
        assert abs(result[("test", "iri1")] - 0.85) < 1e-9

    def test_handles_markdown_code_block(self):
        raw = '```json\n{"scores": [{"concept_text": "Test", "folio_iri": "iri1", "contextual_score": 0.75}]}\n```'
        result = ContextualRerankStage._parse_scores(raw)
        assert ("test", "iri1") in result

    def test_clamps_scores(self):
        raw = json.dumps({
            "scores": [
                {"concept_text": "a", "folio_iri": "iri", "contextual_score": 1.5},
                {"concept_text": "b", "folio_iri": "iri2", "contextual_score": -0.3},
            ]
        })
        result = ContextualRerankStage._parse_scores(raw)
        assert result[("a", "iri")] == 1.0
        assert result[("b", "iri2")] == 0.0

    def test_returns_empty_on_garbage(self):
        assert ContextualRerankStage._parse_scores("not json") == {}
        assert ContextualRerankStage._parse_scores("") == {}
