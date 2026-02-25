"""Pass 4 — Merge and deduplicate individuals from all three sources."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.annotation import Individual, IndividualClassLink, StageEvent

logger = logging.getLogger(__name__)

# Source priority: higher = wins on conflict
_SOURCE_PRIORITY = {
    "eyecite": 100,
    "citeurl": 95,
    "regex": 80,
    "spacy_ner": 70,
    "llm": 50,
}


def _priority(source: str) -> int:
    return _SOURCE_PRIORITY.get(source, 0)


def _spans_overlap(a: Individual, b: Individual) -> bool:
    """Check if two individuals have overlapping spans."""
    return a.span.start < b.span.end and b.span.start < a.span.end


def _names_match(a: Individual, b: Individual) -> bool:
    """Check if two individuals refer to the same entity by name."""
    a_name = a.name.lower().strip()
    b_name = b.name.lower().strip()

    # Exact match
    if a_name == b_name:
        return True

    # One is a substring of the other (e.g., "Smith" vs "John Smith")
    if a_name in b_name or b_name in a_name:
        return True

    # Mention text match
    a_mention = a.mention_text.lower().strip()
    b_mention = b.mention_text.lower().strip()
    if a_mention == b_mention:
        return True

    return False


def _merge_class_links(
    winner: Individual, loser: Individual
) -> list[IndividualClassLink]:
    """Merge class links from loser into winner, avoiding duplicates."""
    existing = {
        (l.annotation_id, l.folio_label, l.folio_iri)
        for l in winner.class_links
    }
    merged = list(winner.class_links)
    for link in loser.class_links:
        key = (link.annotation_id, link.folio_label, link.folio_iri)
        if key not in existing:
            merged.append(link)
            existing.add(key)
    return merged


def deduplicate(individuals: list[Individual]) -> list[Individual]:
    """Merge overlapping/matching individuals, preferring higher-priority sources.

    Strategy:
    1. Sort by source priority (highest first)
    2. For each individual, check if it overlaps/matches any already-kept individual
    3. If match found: merge class links from the new individual into the existing one
    4. If no match: add as new
    """
    if not individuals:
        return []

    # Sort by priority descending, then by span start
    sorted_inds = sorted(
        individuals,
        key=lambda i: (-_priority(i.source), i.span.start),
    )

    kept: list[Individual] = []

    for ind in sorted_inds:
        matched_idx = None
        for idx, existing in enumerate(kept):
            if _spans_overlap(ind, existing) or _names_match(ind, existing):
                matched_idx = idx
                break

        if matched_idx is not None:
            existing = kept[matched_idx]
            # Merge class links from lower-priority into higher-priority
            existing.class_links = _merge_class_links(existing, ind)

            # If the new one has a URL and the existing doesn't, take it
            if ind.url and not existing.url:
                existing.url = ind.url

            # If the new one has a normalized form and the existing doesn't, take it
            if ind.normalized_form and not existing.normalized_form:
                existing.normalized_form = ind.normalized_form

            # Mark as hybrid if sources differ
            if ind.source != existing.source:
                existing.source = "hybrid"

            # Add merge lineage
            existing.lineage.append(
                StageEvent(
                    stage="individual_extraction",
                    action="merged",
                    detail=f"merged with {ind.source} match: {ind.name}",
                    confidence=existing.confidence,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
        else:
            kept.append(ind)

    logger.info(
        "Deduplication: %d individuals → %d unique",
        len(individuals),
        len(kept),
    )
    return kept
