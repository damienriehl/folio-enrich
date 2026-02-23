from __future__ import annotations

from typing import Any

import pytest

from app.models.document import TextChunk
from app.services.concept.llm_concept_identifier import LLMConceptIdentifier
from app.services.llm.base import LLMProvider


class FakeLLMProvider(LLMProvider):
    """Returns pre-configured concept identification results."""

    _DEFAULTS = [
        {"concept_text": "breach of contract", "branch_hint": "Legal Concepts", "confidence": 0.95},
        {"concept_text": "damages", "branch_hint": "Legal Concepts", "confidence": 0.88},
    ]

    def __init__(self, concepts: list[dict] | None = None):
        self.concepts = self._DEFAULTS if concepts is None else concepts

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        return {"concepts": self.concepts}

    async def test_connection(self) -> bool:
        return True

    async def list_models(self):
        return []


class FailingLLMProvider(LLMProvider):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        raise RuntimeError("LLM error")

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        raise RuntimeError("LLM error")

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        raise RuntimeError("LLM error")

    async def test_connection(self) -> bool:
        return False

    async def list_models(self):
        return []


class TestLLMConceptIdentifier:
    @pytest.mark.asyncio
    async def test_identify_concepts(self):
        llm = FakeLLMProvider()
        identifier = LLMConceptIdentifier(llm)
        chunk = TextChunk(text="The breach of contract resulted in damages.", start_offset=0, end_offset=44, chunk_index=0)

        concepts = await identifier.identify_concepts(chunk)
        assert len(concepts) == 2
        assert concepts[0].concept_text == "breach of contract"
        assert concepts[0].branch == "Legal Concepts"
        assert concepts[0].confidence == 0.95
        assert concepts[0].source == "llm"

    @pytest.mark.asyncio
    async def test_identify_concepts_empty(self):
        llm = FakeLLMProvider(concepts=[])
        identifier = LLMConceptIdentifier(llm)
        chunk = TextChunk(text="No legal content here.", start_offset=0, end_offset=22, chunk_index=0)

        concepts = await identifier.identify_concepts(chunk)
        assert len(concepts) == 0

    @pytest.mark.asyncio
    async def test_identify_concepts_handles_error(self):
        llm = FailingLLMProvider()
        identifier = LLMConceptIdentifier(llm)
        chunk = TextChunk(text="Some text.", start_offset=0, end_offset=10, chunk_index=0)

        concepts = await identifier.identify_concepts(chunk)
        assert len(concepts) == 0  # Graceful degradation

    @pytest.mark.asyncio
    async def test_identify_concepts_batch(self):
        llm = FakeLLMProvider()
        identifier = LLMConceptIdentifier(llm)
        chunks = [
            TextChunk(text="First chunk about contract law.", start_offset=0, end_offset=31, chunk_index=0),
            TextChunk(text="Second chunk about tort law.", start_offset=31, end_offset=59, chunk_index=1),
        ]

        results = await identifier.identify_concepts_batch(chunks)
        assert len(results) == 2
        assert 0 in results
        assert 1 in results
        assert len(results[0]) == 2
        assert len(results[1]) == 2
