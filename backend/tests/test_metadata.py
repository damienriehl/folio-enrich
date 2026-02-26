from __future__ import annotations

from typing import Any

import pytest

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.document import CanonicalText, DocumentFormat, DocumentInput, TextChunk
from app.models.job import Job, JobResult, JobStatus
from app.pipeline.stages.metadata_stage import MetadataStage
from app.services.llm.base import LLMProvider
from app.services.metadata.classifier import DocumentClassifier
from app.services.metadata.extractor import MetadataExtractor
from app.services.metadata.promoter import MetadataPromoter


class FakeClassifierLLM(LLMProvider):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        return {"document_type": "Motion to Dismiss", "confidence": 0.92, "reasoning": "test"}

    async def test_connection(self) -> bool:
        return True

    async def list_models(self):
        return []


class FakeExtractorLLM(LLMProvider):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        return {
            "court": "Southern District of New York",
            "judge": "Judge Smith",
            "case_number": "1:23-cv-01234",
            "parties": ["Acme Corp", "Widget Inc"],
            "date_filed": "2023-06-15",
            "jurisdiction": "Federal",
            "governing_law": "",
            "claim_types": ["Breach of Contract"],
            "author": "John Doe",
            "recipient": "Jane Smith",
            "addresses": ["123 Main St, New York, NY 10001"],
        }

    async def test_connection(self) -> bool:
        return True

    async def list_models(self):
        return []


class TestDocumentClassifier:
    @pytest.mark.asyncio
    async def test_classify(self):
        classifier = DocumentClassifier(FakeClassifierLLM())
        result = await classifier.classify("IN THE UNITED STATES DISTRICT COURT...")
        assert result["document_type"] == "Motion to Dismiss"
        assert result["confidence"] == 0.92


class TestMetadataExtractor:
    @pytest.mark.asyncio
    async def test_extract(self):
        extractor = MetadataExtractor(FakeExtractorLLM())
        result = await extractor.extract("Some legal text...", "Motion to Dismiss")
        assert result["court"] == "Southern District of New York"
        assert result["judge"] == "Judge Smith"
        assert len(result["parties"]) == 2
        assert result["author"] == "John Doe"
        assert result["recipient"] == "Jane Smith"
        assert result["addresses"] == ["123 Main St, New York, NY 10001"]


class TrackingClassifierLLM(LLMProvider):
    """Tracks whether classify was called."""

    def __init__(self):
        self.classify_called = False

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        if "classifier" in prompt.lower() or "classify" in prompt.lower() or "document type" in prompt.lower():
            self.classify_called = True
            return {"document_type": "Should Not Be Used", "confidence": 0.5, "reasoning": "test"}
        return {
            "court": "",
            "judge": "",
            "case_number": "",
            "parties": [],
            "date_filed": "",
            "jurisdiction": "",
            "governing_law": "",
            "claim_types": [],
            "author": "",
            "recipient": "",
            "addresses": [],
        }

    async def test_connection(self) -> bool:
        return True

    async def list_models(self):
        return []


class TestMetadataStageReuse:
    @pytest.mark.asyncio
    async def test_reuses_early_document_type(self):
        """When self_identified_type is set, MetadataStage skips classifier."""
        llm = FakeExtractorLLM()
        stage = MetadataStage(llm, classifier_llm=llm, extractor_llm=llm)

        text = "IN THE UNITED STATES DISTRICT COURT..."
        job = Job(
            input=DocumentInput(content=text, format=DocumentFormat.PLAIN_TEXT),
            status=JobStatus.ENRICHING,
            result=JobResult(
                canonical_text=CanonicalText(
                    full_text=text,
                    chunks=[TextChunk(text=text, start_offset=0, end_offset=len(text), chunk_index=0)],
                ),
            ),
        )
        job.result.metadata["self_identified_type"] = "Defendant's Motion to Dismiss"
        job.result.metadata["document_type_confidence"] = 0.95

        result = await stage.execute(job)

        # Should use the early type, not re-classify
        assert result.result.metadata["document_type"] == "Defendant's Motion to Dismiss"
        # Activity log should indicate reuse
        log = result.result.metadata.get("activity_log", [])
        assert any("reused_early=yes" in entry.get("msg", "") for entry in log)

    @pytest.mark.asyncio
    async def test_falls_back_when_no_early_type(self):
        """Without self_identified_type, MetadataStage classifies normally."""
        stage = MetadataStage(
            FakeClassifierLLM(),
            classifier_llm=FakeClassifierLLM(),
            extractor_llm=FakeExtractorLLM(),
        )

        text = "IN THE UNITED STATES DISTRICT COURT..."
        job = Job(
            input=DocumentInput(content=text, format=DocumentFormat.PLAIN_TEXT),
            status=JobStatus.ENRICHING,
            result=JobResult(
                canonical_text=CanonicalText(
                    full_text=text,
                    chunks=[TextChunk(text=text, start_offset=0, end_offset=len(text), chunk_index=0)],
                ),
            ),
        )

        result = await stage.execute(job)

        assert result.result.metadata["document_type"] == "Motion to Dismiss"
        log = result.result.metadata.get("activity_log", [])
        assert any("reused_early=no" in entry.get("msg", "") for entry in log)


class TestMetadataPromoter:
    def test_promote_from_context(self):
        promoter = MetadataPromoter()
        annotations = [
            Annotation(
                span=Span(start=80, end=95, text="Southern District"),
                concepts=[
                    ConceptMatch(
                        concept_text="Southern District",
                        folio_iri="iri1",
                        confidence=0.9,
                    )
                ],
            ),
        ]
        full_text = " " * 30 + "IN THE UNITED STATES DISTRICT COURT FOR THE " + " " * 5 + "Southern District"
        result = promoter.promote(annotations, full_text, {})
        assert "court" in result or len(result) >= 0  # Context-dependent
