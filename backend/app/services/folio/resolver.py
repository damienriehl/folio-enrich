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
        folio_iri: str | None = None,
    ) -> ResolvedConcept | None:
        """Resolve a concept to a FOLIO concept.

        If folio_iri is provided, look up the concept directly by IRI (fast path).
        Otherwise, search by label text (slow path with potential mismatches).
        """
        cache_key = (concept_text.lower(), branch.lower())
        if cache_key in self._cache:
            return self._cache[cache_key]

        best_concept = None
        score = 0.0

        # Fast path: direct IRI lookup (used by EntityRuler which already knows the IRI)
        if folio_iri:
            direct = self.folio.get_concept(folio_iri)
            if direct:
                best_concept = direct
                score = confidence  # Trust the confidence from the caller
            else:
                logger.warning("IRI lookup failed for %s, falling back to search", folio_iri)

        # Slow path: search by label text
        if best_concept is None:
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
                c.get("folio_iri"),
            )
            for c in concepts
        ]

    @property
    def cache_size(self) -> int:
        return len(self._cache)
