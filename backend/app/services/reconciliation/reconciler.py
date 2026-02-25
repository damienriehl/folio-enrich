from __future__ import annotations

import logging
from dataclasses import dataclass

from app.models.annotation import ConceptMatch

logger = logging.getLogger(__name__)


def _definition_overlap_score(context: str, definition: str) -> float:
    """Compute word overlap between context and definition as a simple semantic signal."""
    if not context or not definition:
        return 0.0
    ctx_words = set(context.lower().split())
    def_words = set(definition.lower().split())
    # Remove very common words
    stopwords = {"the", "a", "an", "of", "to", "in", "for", "and", "or", "is", "on", "at", "by", "with"}
    ctx_words -= stopwords
    def_words -= stopwords
    if not ctx_words or not def_words:
        return 0.0
    return len(ctx_words & def_words) / max(len(ctx_words), len(def_words))

EMBEDDING_AUTO_RESOLVE_THRESHOLD = 0.85


def _diminishing_boost(base: float, max_boost: float = 0.05) -> float:
    """Apply a diminishing confidence boost: high scores barely change, low scores get meaningful lift."""
    return max_boost * (1.0 - base)


# Ruler-only concepts need at least this confidence to be accepted
# This filters out low-confidence single-word alt-label matches (conf=0.35)
# while keeping preferred labels (conf=0.72+) and multi-word matches (conf>=0.65)
RULER_ONLY_MIN_CONFIDENCE = 0.60


@dataclass
class ReconciliationResult:
    concept: ConceptMatch
    category: str  # "both_agree", "ruler_only", "llm_only", "conflict_resolved"


def _build_text_and_key_maps(concepts: list[ConceptMatch]) -> tuple[
    dict[tuple[str, str], ConceptMatch],
    dict[str, list[ConceptMatch]],
]:
    """Build (text,IRI)-keyed map and text-only grouped map from concepts."""
    by_key: dict[tuple[str, str], ConceptMatch] = {}
    by_text: dict[str, list[ConceptMatch]] = {}
    for c in concepts:
        k = (c.concept_text.lower(), c.folio_iri or "")
        by_key[k] = c
        by_text.setdefault(c.concept_text.lower(), []).append(c)
    return by_key, by_text


class Reconciler:
    """Merge EntityRuler and LLM concept identification results."""

    def __init__(self, embedding_service=None) -> None:
        self._embedding_service = embedding_service

    def reconcile(
        self,
        ruler_concepts: list[ConceptMatch],
        llm_concepts: list[ConceptMatch],
    ) -> list[ReconciliationResult]:
        ruler_by_key, ruler_by_text = _build_text_and_key_maps(ruler_concepts)
        llm_by_key, llm_by_text = _build_text_and_key_maps(llm_concepts)

        results: list[ReconciliationResult] = []
        handled_ruler_keys: set[tuple[str, str]] = set()
        handled_llm_keys: set[tuple[str, str]] = set()

        # Pass 1: Exact (text, IRI) matching — both sides have matching IRI
        all_keys = set(ruler_by_key.keys()) | set(llm_by_key.keys())
        for key in all_keys:
            text, iri = key
            in_ruler = key in ruler_by_key
            in_llm = key in llm_by_key

            if in_ruler and in_llm:
                concept = llm_by_key[key]
                base = max(ruler_by_key[key].confidence, llm_by_key[key].confidence)
                concept.confidence = min(1.0, base + _diminishing_boost(base))
                concept.source = "reconciled"
                results.append(ReconciliationResult(concept=concept, category="both_agree"))
                handled_ruler_keys.add(key)
                handled_llm_keys.add(key)

        # Pass 2: Cross-match empty-IRI concepts by text alone
        for key, concept in ruler_by_key.items():
            if key in handled_ruler_keys:
                continue
            text, iri = key
            if not iri:
                # Empty-IRI ruler concept — try to match any LLM concept with same text
                for lc in llm_by_text.get(text, []):
                    lkey = (text, lc.folio_iri or "")
                    if lkey not in handled_llm_keys:
                        base = max(concept.confidence, lc.confidence)
                        lc.confidence = min(1.0, base + _diminishing_boost(base))
                        lc.source = "reconciled"
                        results.append(ReconciliationResult(concept=lc, category="both_agree"))
                        handled_ruler_keys.add(key)
                        handled_llm_keys.add(lkey)
                        break

        for key, concept in llm_by_key.items():
            if key in handled_llm_keys:
                continue
            text, iri = key
            if not iri:
                # Empty-IRI LLM concept — try to match any ruler concept with same text
                for rc in ruler_by_text.get(text, []):
                    rkey = (text, rc.folio_iri or "")
                    if rkey not in handled_ruler_keys:
                        base = max(concept.confidence, rc.confidence)
                        rc.confidence = min(1.0, base + _diminishing_boost(base))
                        rc.source = "reconciled"
                        results.append(ReconciliationResult(concept=rc, category="both_agree"))
                        handled_llm_keys.add(key)
                        handled_ruler_keys.add(rkey)
                        break

        # Pass 3: Remaining unmatched concepts
        for key, concept in ruler_by_key.items():
            if key in handled_ruler_keys:
                continue
            if concept.confidence >= RULER_ONLY_MIN_CONFIDENCE:
                concept.source = "entity_ruler"
                results.append(ReconciliationResult(concept=concept, category="ruler_only"))
            else:
                logger.debug(
                    "Filtered ruler-only concept '%s' (confidence=%.2f < %.2f threshold)",
                    key, concept.confidence, RULER_ONLY_MIN_CONFIDENCE,
                )

        for key, concept in llm_by_key.items():
            if key in handled_llm_keys:
                continue
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

        ruler_by_key, ruler_by_text = _build_text_and_key_maps(ruler_concepts)
        llm_by_key, llm_by_text = _build_text_and_key_maps(llm_concepts)

        results: list[ReconciliationResult] = []
        handled_ruler_keys: set[tuple[str, str]] = set()
        handled_llm_keys: set[tuple[str, str]] = set()
        conflicts: list[tuple[str, ConceptMatch, ConceptMatch]] = []

        # Pass 1: Exact (text, IRI) matching
        all_keys = set(ruler_by_key.keys()) | set(llm_by_key.keys())
        for key in all_keys:
            text, iri = key
            in_ruler = key in ruler_by_key
            in_llm = key in llm_by_key

            if in_ruler and in_llm:
                rc = ruler_by_key[key]
                lc = llm_by_key[key]
                if rc.folio_iri and lc.folio_iri and rc.folio_iri == lc.folio_iri:
                    concept = lc
                    base = max(rc.confidence, lc.confidence)
                    concept.confidence = min(1.0, base + _diminishing_boost(base))
                    concept.source = "reconciled"
                    results.append(ReconciliationResult(concept=concept, category="both_agree"))
                else:
                    concept = lc
                    base = max(rc.confidence, lc.confidence)
                    concept.confidence = min(1.0, base + _diminishing_boost(base))
                    concept.source = "reconciled"
                    results.append(ReconciliationResult(concept=concept, category="both_agree"))
                handled_ruler_keys.add(key)
                handled_llm_keys.add(key)

        # Pass 2: Cross-match empty-IRI concepts by text, handling IRI asymmetry
        for key, concept in ruler_by_key.items():
            if key in handled_ruler_keys:
                continue
            text, iri = key
            for lc in llm_by_text.get(text, []):
                lkey = (text, lc.folio_iri or "")
                if lkey in handled_llm_keys:
                    continue

                rc = concept
                # One or both have no IRI — merge
                if not rc.folio_iri or not lc.folio_iri:
                    winner = rc if rc.folio_iri else lc
                    base = max(rc.confidence, lc.confidence)
                    winner.confidence = min(1.0, base + _diminishing_boost(base))
                    winner.source = "reconciled"
                    results.append(ReconciliationResult(concept=winner, category="both_agree"))
                    handled_ruler_keys.add(key)
                    handled_llm_keys.add(lkey)
                    break
                # Both have IRIs but they differ — IRI conflict for embedding triage
                elif rc.folio_iri != lc.folio_iri:
                    conflicts.append((text, rc, lc))
                    handled_ruler_keys.add(key)
                    handled_llm_keys.add(lkey)
                    break

        for key, concept in llm_by_key.items():
            if key in handled_llm_keys:
                continue
            text, iri = key
            if not iri:
                for rc in ruler_by_text.get(text, []):
                    rkey = (text, rc.folio_iri or "")
                    if rkey in handled_ruler_keys:
                        continue
                    winner = rc if rc.folio_iri else concept
                    base = max(concept.confidence, rc.confidence)
                    winner.confidence = min(1.0, base + _diminishing_boost(base))
                    winner.source = "reconciled"
                    results.append(ReconciliationResult(concept=winner, category="both_agree"))
                    handled_llm_keys.add(key)
                    handled_ruler_keys.add(rkey)
                    break

        # Pass 3: Remaining unmatched
        for key, concept in ruler_by_key.items():
            if key in handled_ruler_keys:
                continue
            if concept.confidence >= RULER_ONLY_MIN_CONFIDENCE:
                concept.source = "entity_ruler"
                results.append(ReconciliationResult(concept=concept, category="ruler_only"))
            else:
                logger.debug(
                    "Filtered ruler-only concept '%s' (confidence=%.2f < %.2f threshold)",
                    key, concept.confidence, RULER_ONLY_MIN_CONFIDENCE,
                )

        for key, concept in llm_by_key.items():
            if key in handled_llm_keys:
                continue
            concept.source = "llm"
            results.append(ReconciliationResult(concept=concept, category="llm_only"))

        # Batch resolve IRI conflicts via embedding similarity
        if conflicts:
            pairs = []
            for text, rc, lc in conflicts:
                ruler_label = rc.folio_label or rc.concept_text
                llm_label = lc.folio_label or lc.concept_text
                pairs.append((text, ruler_label))
                pairs.append((text, llm_label))

            sims = self._embedding_service.similarity_batch(pairs)

            for i, (text, rc, lc) in enumerate(conflicts):
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
                    # Both below threshold — try definition-based tiebreaker
                    rc_defn = rc.folio_definition or ""
                    lc_defn = lc.folio_definition or ""
                    if rc_defn or lc_defn:
                        rc_overlap = _definition_overlap_score(text, rc_defn)
                        lc_overlap = _definition_overlap_score(text, lc_defn)
                        if rc_overlap > lc_overlap and rc_overlap > 0:
                            rc.source = "reconciled"
                            results.append(ReconciliationResult(concept=rc, category="conflict_resolved"))
                            continue
                        elif lc_overlap > rc_overlap and lc_overlap > 0:
                            lc.source = "reconciled"
                            results.append(ReconciliationResult(concept=lc, category="conflict_resolved"))
                            continue
                    # No clear winner — keep both
                    rc.source = "reconciled"
                    lc.source = "reconciled"
                    results.append(ReconciliationResult(concept=rc, category="conflict_resolved"))
                    results.append(ReconciliationResult(concept=lc, category="conflict_resolved"))

        return results
