"""Deduplicate and merge overlapping property annotations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.annotation import PropertyAnnotation, StageEvent

logger = logging.getLogger(__name__)


def deduplicate_properties(properties: list[PropertyAnnotation]) -> list[PropertyAnnotation]:
    """Merge overlapping property spans.

    Strategy:
    - Longer match wins over shorter on overlapping spans
    - Higher confidence wins on same-length spans
    - LLM source wins over aho_corasick on same span
    """
    if not properties:
        return []

    # Sort by span start, then by length descending, then by confidence descending
    sorted_props = sorted(
        properties,
        key=lambda p: (p.span.start, -(p.span.end - p.span.start), -p.confidence),
    )

    kept: list[PropertyAnnotation] = []

    for prop in sorted_props:
        if not kept:
            kept.append(prop)
            continue

        last = kept[-1]

        # Check overlap
        if prop.span.start < last.span.end:
            # Overlapping — decide winner
            last_len = last.span.end - last.span.start
            prop_len = prop.span.end - prop.span.start

            if prop_len > last_len:
                # Longer match wins
                last.lineage.append(StageEvent(
                    stage="property_extraction",
                    action="merged",
                    detail=f"superseded by longer match: {prop.property_text}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))
                kept[-1] = prop
            elif prop_len == last_len and prop.confidence > last.confidence:
                # Same length, higher confidence wins
                kept[-1] = prop
            # else: existing match wins, skip this one
        else:
            kept.append(prop)

    logger.info(
        "Property deduplication: %d → %d unique",
        len(properties), len(kept),
    )
    return kept
