from __future__ import annotations

import logging
from dataclasses import dataclass

from app.models.annotation import ConceptMatch

logger = logging.getLogger(__name__)

EMBEDDING_AUTO_RESOLVE_THRESHOLD = 0.85


@dataclass
class ReconciliationResult:
    concept: ConceptMatch
    category: str  # "both_agree", "ruler_only", "llm_only", "conflict_resolved"


class Reconciler:
    """Merge EntityRuler and LLM concept identification results."""

    def __init__(self, embedding_service=None) -> None:
        self._embedding_service = embedding_service

    def reconcile(
        self,
        ruler_concepts: list[ConceptMatch],
        llm_concepts: list[ConceptMatch],
    ) -> list[ReconciliationResult]:
        ruler_by_text = {c.concept_text.lower(): c for c in ruler_concepts}
        llm_by_text = {c.concept_text.lower(): c for c in llm_concepts}

        all_keys = set(ruler_by_text.keys()) | set(llm_by_text.keys())
        results: list[ReconciliationResult] = []

        for key in all_keys:
            in_ruler = key in ruler_by_text
            in_llm = key in llm_by_text

            if in_ruler and in_llm:
                # Both agree: accept with boosted confidence
                concept = llm_by_text[key]
                concept.confidence = min(
                    1.0, max(ruler_by_text[key].confidence, llm_by_text[key].confidence) + 0.05
                )
                concept.source = "reconciled"
                results.append(ReconciliationResult(concept=concept, category="both_agree"))

            elif in_ruler and not in_llm:
                # EntityRuler only: accept if multi-word or high confidence
                concept = ruler_by_text[key]
                if len(key.split()) > 1 or concept.confidence >= 0.8:
                    concept.source = "entity_ruler"
                    results.append(ReconciliationResult(concept=concept, category="ruler_only"))

            elif in_llm and not in_ruler:
                # LLM only: accept, mark as contextual
                concept = llm_by_text[key]
                concept.source = "llm"
                results.append(ReconciliationResult(concept=concept, category="llm_only"))

        return results

    def reconcile_with_embedding_triage(
        self,
        ruler_concepts: list[ConceptMatch],
        llm_concepts: list[ConceptMatch],
    ) -> list[ReconciliationResult]:
        """Enhanced reconciliation that uses embedding similarity for conflict resolution."""
        # For now, delegate to basic reconciliation
        # Embedding triage will enhance this when both paths identify different concepts
        # for the same text span (a true conflict scenario)
        return self.reconcile(ruler_concepts, llm_concepts)
