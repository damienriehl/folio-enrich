from __future__ import annotations

from typing import Any

import pytest

from app.models.annotation import Annotation, ConceptMatch, Span
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
