from __future__ import annotations

import logging

from app.models.annotation import Annotation

logger = logging.getLogger(__name__)

# Annotations in these positions suggest metadata fields
POSITION_HINTS = {
    "signatory": ["signature", "signed by", "executed by"],
    "court": ["in the", "united states district court", "court of"],
    "judge": ["honorable", "judge", "justice"],
}


class MetadataPromoter:
    """Promote high-confidence annotations to document metadata based on structural position."""

    def promote(
        self, annotations: list[Annotation], full_text: str, existing_metadata: dict
    ) -> dict:
        promoted = dict(existing_metadata)

        for ann in annotations:
            if not ann.concepts:
                continue

            concept = ann.concepts[0]
            context_start = max(0, ann.span.start - 50)
            context = full_text[context_start : ann.span.start].lower()

            # Check if annotation's surrounding text suggests a metadata field
            for field, hints in POSITION_HINTS.items():
                if any(hint in context for hint in hints):
                    if field not in promoted or not promoted[field]:
                        promoted[field] = concept.concept_text
                        break

        return promoted
