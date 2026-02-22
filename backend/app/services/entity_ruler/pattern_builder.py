from __future__ import annotations

from app.services.folio.folio_service import FOLIOConcept


def build_patterns(concepts: dict[str, FOLIOConcept]) -> list[dict]:
    """Build spaCy EntityRuler patterns from FOLIO concept labels."""
    patterns = []
    seen: set[str] = set()

    for label, concept in concepts.items():
        if not label or label in seen:
            continue
        seen.add(label)

        # Create pattern from label tokens
        tokens = label.split()
        if len(tokens) == 1:
            pattern = {"label": "FOLIO_CONCEPT", "pattern": label, "id": concept.iri}
        else:
            pattern = {
                "label": "FOLIO_CONCEPT",
                "pattern": [{"LOWER": t.lower()} for t in tokens],
                "id": concept.iri,
            }
        patterns.append(pattern)

    return patterns
