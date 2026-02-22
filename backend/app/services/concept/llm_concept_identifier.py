from __future__ import annotations

import logging
from typing import Any

from app.models.annotation import ConceptMatch
from app.models.document import TextChunk
from app.services.llm.base import LLMProvider
from app.services.llm.prompts.concept_identification import (
    build_concept_identification_prompt,
)

logger = logging.getLogger(__name__)


class LLMConceptIdentifier:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def identify_concepts(self, chunk: TextChunk) -> list[ConceptMatch]:
        prompt = build_concept_identification_prompt(chunk.text)

        try:
            result = await self.llm.structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "concepts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "concept_text": {"type": "string"},
                                    "branch_hint": {"type": "string"},
                                    "confidence": {"type": "number"},
                                },
                            },
                        }
                    },
                },
            )
        except Exception:
            logger.exception("LLM concept identification failed for chunk %d", chunk.chunk_index)
            return []

        concepts = []
        for item in result.get("concepts", []):
            concepts.append(
                ConceptMatch(
                    concept_text=item.get("concept_text", ""),
                    branch=item.get("branch_hint"),
                    confidence=item.get("confidence", 0.0),
                    source="llm",
                )
            )
        return concepts

    async def identify_concepts_batch(
        self, chunks: list[TextChunk]
    ) -> dict[int, list[ConceptMatch]]:
        import asyncio

        tasks = [self.identify_concepts(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output: dict[int, list[ConceptMatch]] = {}
        for chunk, result in zip(chunks, results):
            if isinstance(result, Exception):
                logger.error("Chunk %d failed: %s", chunk.chunk_index, result)
                output[chunk.chunk_index] = []
            else:
                output[chunk.chunk_index] = result
        return output
