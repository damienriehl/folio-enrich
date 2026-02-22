from __future__ import annotations

from app.services.folio.folio_service import FOLIOConcept


MIN_PATTERN_LENGTH = 3  # Skip patterns shorter than 3 characters

# Common English words that are false positive matches for FOLIO concepts
_STOPWORDS = frozenset({
    "a", "an", "the", "to", "of", "in", "on", "at", "by", "for", "or",
    "and", "is", "it", "be", "as", "do", "no", "so", "up", "if", "my",
    "me", "he", "we", "am", "us", "go", "re", "al", "de", "la", "le",
    "mr", "ms", "dr", "st", "vs", "id", "ie", "eg", "etc", "per", "via",
    "not", "but", "has", "had", "was", "are", "its", "may", "can", "did",
    "she", "his", "her", "him", "our", "who", "how", "all", "any", "new",
    "one", "two", "out", "own", "set", "use", "way", "day", "get", "see",
    "now", "old", "end", "put", "run", "let", "say", "too", "yet", "off",
    "try", "ask", "got", "met", "cut", "pay", "due", "add",
})


def build_patterns(concepts: dict[str, FOLIOConcept]) -> list[dict]:
    """Build spaCy EntityRuler patterns from FOLIO concept labels."""
    patterns = []
    seen: set[str] = set()

    for label, concept in concepts.items():
        if not label or label in seen:
            continue
        seen.add(label)

        # Skip very short labels and common stopwords
        if len(label) < MIN_PATTERN_LENGTH:
            continue
        if label.lower() in _STOPWORDS:
            continue

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
