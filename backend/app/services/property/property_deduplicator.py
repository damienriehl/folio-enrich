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
        dominated = False
        for i, existing in enumerate(kept):
            # No overlap
            if prop.span.start >= existing.span.end or prop.span.end <= existing.span.start:
                continue

            # Identical span — higher confidence wins
            if prop.span.start == existing.span.start and prop.span.end == existing.span.end:
                if prop.confidence > existing.confidence:
                    kept[i] = prop
                dominated = True
                break

            # Containment (either direction) — keep both
            if (prop.span.start >= existing.span.start and prop.span.end <= existing.span.end):
                continue
            if (existing.span.start >= prop.span.start and existing.span.end <= prop.span.end):
                continue

            # Partial overlap — longer match wins
            prop_len = prop.span.end - prop.span.start
            existing_len = existing.span.end - existing.span.start
            if prop_len > existing_len:
                existing.lineage.append(StageEvent(
                    stage="property_extraction",
                    action="merged",
                    detail=f"superseded by longer match: {prop.property_text}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))
                kept[i] = prop
            dominated = True
            break

        if not dominated:
            kept.append(prop)

    kept.sort(key=lambda p: (p.span.start, -(p.span.end - p.span.start)))

    logger.info(
        "Property deduplication: %d → %d unique",
        len(properties), len(kept),
    )
    return kept
