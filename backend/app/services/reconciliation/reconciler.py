from __future__ import annotations

import logging
from dataclasses import dataclass

from app.models.annotation import ConceptMatch

logger = logging.getLogger(__name__)

EMBEDDING_AUTO_RESOLVE_THRESHOLD = 0.85

# Ruler-only concepts need at least this confidence to be accepted
# This filters out low-confidence single-word alt-label matches (conf=0.35)
# while keeping preferred labels (conf=0.80) and multi-word matches (conf>=0.65)
RULER_ONLY_MIN_CONFIDENCE = 0.60


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
                # EntityRuler only: accept based on confidence threshold
                # Multi-word preferred (0.95) and single-word preferred (0.80) pass
                # Multi-word alt (0.65) passes
                # Single-word alt (0.35) is rejected — too many false positives
                concept = ruler_by_text[key]
                if concept.confidence >= RULER_ONLY_MIN_CONFIDENCE:
                    concept.source = "entity_ruler"
                    results.append(ReconciliationResult(concept=concept, category="ruler_only"))
                else:
                    logger.debug(
                        "Filtered ruler-only concept '%s' (confidence=%.2f < %.2f threshold)",
                        key, concept.confidence, RULER_ONLY_MIN_CONFIDENCE,
                    )

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
        """Enhanced reconciliation that uses embedding similarity for conflict resolution.

        When ruler and LLM identify the same text span but map to different FOLIO
        concepts, compute cosine similarity between each candidate label and the
        original text to pick the better match.  Similarity pairs are batch-embedded
        in a single forward pass.
        """
        if self._embedding_service is None or self._embedding_service.index_size == 0:
            return self.reconcile(ruler_concepts, llm_concepts)

        ruler_by_text = {c.concept_text.lower(): c for c in ruler_concepts}
        llm_by_text = {c.concept_text.lower(): c for c in llm_concepts}
        all_keys = set(ruler_by_text.keys()) | set(llm_by_text.keys())
        results: list[ReconciliationResult] = []

        # First pass: categorize keys and collect IRI conflicts for batch resolution
        conflicts: list[tuple[str, ConceptMatch, ConceptMatch]] = []

        for key in all_keys:
            in_ruler = key in ruler_by_text
            in_llm = key in llm_by_text

            if in_ruler and in_llm:
                rc = ruler_by_text[key]
                lc = llm_by_text[key]

                if rc.folio_iri and lc.folio_iri and rc.folio_iri == lc.folio_iri:
                    concept = lc
                    concept.confidence = min(1.0, max(rc.confidence, lc.confidence) + 0.05)
                    concept.source = "reconciled"
                    results.append(ReconciliationResult(concept=concept, category="both_agree"))
                elif rc.folio_iri and lc.folio_iri:
                    conflicts.append((key, rc, lc))
                else:
                    concept = lc
                    concept.confidence = min(1.0, max(rc.confidence, lc.confidence) + 0.05)
                    concept.source = "reconciled"
                    results.append(ReconciliationResult(concept=concept, category="both_agree"))

            elif in_ruler and not in_llm:
                concept = ruler_by_text[key]
                if concept.confidence >= RULER_ONLY_MIN_CONFIDENCE:
                    concept.source = "entity_ruler"
                    results.append(ReconciliationResult(concept=concept, category="ruler_only"))
                else:
                    logger.debug(
                        "Filtered ruler-only concept '%s' (confidence=%.2f < %.2f threshold)",
                        key, concept.confidence, RULER_ONLY_MIN_CONFIDENCE,
                    )

            elif in_llm and not in_ruler:
                concept = llm_by_text[key]
                concept.source = "llm"
                results.append(ReconciliationResult(concept=concept, category="llm_only"))

        # Batch resolve IRI conflicts via embedding similarity
        if conflicts:
            pairs = []
            for key, rc, lc in conflicts:
                ruler_label = rc.folio_label or rc.concept_text
                llm_label = lc.folio_label or lc.concept_text
                pairs.append((key, ruler_label))
                pairs.append((key, llm_label))

            sims = self._embedding_service.similarity_batch(pairs)

            for i, (key, rc, lc) in enumerate(conflicts):
                ruler_sim = sims[i * 2]
                llm_sim = sims[i * 2 + 1]

                if max(ruler_sim, llm_sim) > EMBEDDING_AUTO_RESOLVE_THRESHOLD:
                    if ruler_sim >= llm_sim:
                        rc.source = "reconciled"
                        rc.confidence = max(rc.confidence, ruler_sim)
                        results.append(ReconciliationResult(concept=rc, category="conflict_resolved"))
                    else:
                        lc.source = "reconciled"
                        lc.confidence = max(lc.confidence, llm_sim)
                        results.append(ReconciliationResult(concept=lc, category="conflict_resolved"))
                else:
                    rc.source = "reconciled"
                    lc.source = "reconciled"
                    results.append(ReconciliationResult(concept=rc, category="conflict_resolved"))
                    results.append(ReconciliationResult(concept=lc, category="conflict_resolved"))

        return results
