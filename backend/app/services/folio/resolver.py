from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.folio.folio_service import FOLIOConcept, FolioService

logger = logging.getLogger(__name__)


@dataclass
class ResolvedConcept:
    concept_text: str
    folio_concept: FOLIOConcept
    confidence: float
    branch: str
    source: str


class ConceptResolver:
    """Resolve-Once-Use-Many: caches resolution of concept text to FOLIO IRIs."""

    def __init__(self, folio_service: FolioService | None = None) -> None:
        self.folio = folio_service or FolioService.get_instance()
        self._cache: dict[tuple[str, str], ResolvedConcept | None] = {}

    def resolve(
        self,
        concept_text: str,
        branch: str = "",
        confidence: float = 0.0,
        source: str = "llm",
    ) -> ResolvedConcept | None:
        cache_key = (concept_text.lower(), branch.lower())
        if cache_key in self._cache:
            return self._cache[cache_key]

        results = self.folio.search_by_label(concept_text, top_k=3)
        if not results:
            self._cache[cache_key] = None
            return None

        best_concept, score = results[0]

        # If branch hint provided, prefer matches in that branch
        if branch:
            for concept, s in results:
                if branch.lower() in concept.branch.lower():
                    best_concept, score = concept, s
                    break

        resolved = ResolvedConcept(
            concept_text=concept_text,
            folio_concept=best_concept,
            confidence=max(confidence, score),
            branch=best_concept.branch or branch,
            source=source,
        )
        self._cache[cache_key] = resolved
        return resolved

    def resolve_batch(
        self,
        concepts: list[dict],
    ) -> list[ResolvedConcept | None]:
        return [
            self.resolve(
                c.get("concept_text", ""),
                c.get("branch", ""),
                c.get("confidence", 0.0),
                c.get("source", "llm"),
            )
            for c in concepts
        ]

    @property
    def cache_size(self) -> int:
        return len(self._cache)
