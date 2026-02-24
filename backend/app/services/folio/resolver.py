from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services.folio.branch_config import EXCLUDED_BRANCHES
from app.services.folio.folio_service import FOLIOConcept, FolioService

logger = logging.getLogger(__name__)


@dataclass
class ResolvedConcept:
    concept_text: str
    folio_concept: FOLIOConcept
    confidence: float
    branches: list[str]
    source: str
    branch_color: str = ""
    hierarchy_path: list[str] = field(default_factory=list)
    iri_hash: str = ""


class ConceptResolver:
    """Resolve-Once-Use-Many: caches resolution of concept text to FOLIO IRIs."""

    def __init__(self, folio_service: FolioService | None = None) -> None:
        self.folio = folio_service or FolioService.get_instance()
        self._cache: dict[tuple[str, str], ResolvedConcept | None] = {}

    def resolve(
        self,
        concept_text: str,
        branches: list[str] | None = None,
        confidence: float = 0.0,
        source: str = "llm",
        folio_iri: str | None = None,
    ) -> ResolvedConcept | None:
        """Resolve a concept to a FOLIO concept.

        If folio_iri is provided, look up the concept directly by IRI (fast path).
        Otherwise, search by label text (slow path with potential mismatches).
        """
        branch = branches[0] if branches else ""
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

        # Slow path: multi-strategy search
        if best_concept is None:
            best_concept, score = self._multi_strategy_resolve(concept_text, branch)
            if best_concept is None:
                self._cache[cache_key] = None
                return None

        # Extract enriched metadata
        iri_hash = best_concept.iri.rsplit("/", 1)[-1] if best_concept.iri else ""
        branch_color = ""
        hierarchy_path: list[str] = []
        try:
            from app.services.folio.branch_config import get_branch_color
            branch_color = get_branch_color(best_concept.branch) if best_concept.branch else ""
        except Exception:
            pass

        resolved_branches = [best_concept.branch] if best_concept.branch else (branches or [])

        # Defense-in-depth: reject concepts from excluded branches
        if any(b in EXCLUDED_BRANCHES for b in resolved_branches):
            self._cache[cache_key] = None
            return None

        resolved = ResolvedConcept(
            concept_text=concept_text,
            folio_concept=best_concept,
            confidence=max(confidence, score),
            branches=resolved_branches,
            source=source,
            branch_color=branch_color,
            hierarchy_path=hierarchy_path,
            iri_hash=iri_hash,
        )
        self._cache[cache_key] = resolved
        return resolved

    def _multi_strategy_resolve(
        self, concept_text: str, branch: str
    ) -> tuple[FOLIOConcept | None, float]:
        """Use multi-strategy search to find the best matching concept."""
        try:
            from app.services.folio.search import multi_strategy_search

            folio_raw = self.folio._get_folio()

            def _get_branch(folio_inst, iri_hash: str) -> str:
                """Resolve branch for a concept IRI hash."""
                owl_class = folio_inst[iri_hash]
                if owl_class and hasattr(owl_class, "iri"):
                    return self.folio._get_branch(owl_class.iri, [])
                return ""

            results = multi_strategy_search(
                folio_raw, concept_text, branch=branch or None, top_n=5,
                get_branch_fn=_get_branch,
            )
            if not results:
                return None, 0.0

            # Convert the best result back to FOLIOConcept
            best = results[0]

            # If branch hint provided, prefer matches in that branch
            if branch:
                for r in results:
                    if r.get("branch") and branch.lower() in r["branch"].lower():
                        best = r
                        break

            concept = FOLIOConcept(
                iri=best["iri"],
                preferred_label=best["label"],
                alternative_labels=best.get("synonyms", []),
                definition=best.get("definition", "") or "",
                branch=best.get("branch", ""),
                parent_iris=[],
            )
            # Normalize score: multi-strategy returns 0-100, convert to 0-1
            score = best["score"] / 100.0
            return concept, score
        except Exception:
            logger.debug(
                "Multi-strategy search failed for '%s', falling back to label search",
                concept_text,
                exc_info=True,
            )
            # Fallback to basic label search
            results = self.folio.search_by_label(concept_text, top_k=3)
            if not results:
                return None, 0.0
            best_concept, score = results[0]
            if branch:
                for concept, s in results:
                    if branch.lower() in concept.branch.lower():
                        best_concept, score = concept, s
                        break
            return best_concept, score

    def resolve_batch(
        self,
        concepts: list[dict],
    ) -> list[ResolvedConcept | None]:
        return [
            self.resolve(
                c.get("concept_text", ""),
                branches=c.get("branches", []),
                confidence=c.get("confidence", 0.0),
                source=c.get("source", "llm"),
                folio_iri=c.get("folio_iri"),
            )
            for c in concepts
        ]

    @property
    def cache_size(self) -> int:
        return len(self._cache)
