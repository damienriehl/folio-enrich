from __future__ import annotations

from app.services.folio.folio_service import LabelInfo


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

# Separator for encoding label_type in pattern ID
_ID_SEP = "|"


def encode_pattern_id(iri: str, label_type: str) -> str:
    """Encode IRI and label_type into a single pattern ID string."""
    return f"{iri}{_ID_SEP}{label_type}"


def decode_pattern_id(pattern_id: str) -> tuple[str, str]:
    """Decode pattern ID back into (iri, label_type)."""
    if _ID_SEP in pattern_id:
        iri, label_type = pattern_id.rsplit(_ID_SEP, 1)
        return iri, label_type
    return pattern_id, "unknown"


def build_patterns(labels: dict[str, LabelInfo]) -> list[dict]:
    """Build spaCy EntityRuler patterns from FOLIO concept labels.

    Encodes label_type (preferred/alternative) in the pattern ID so that
    downstream stages can assign appropriate confidence scores.
    """
    patterns = []
    seen: set[str] = set()

    for label_text, info in labels.items():
        if not label_text or label_text in seen:
            continue
        seen.add(label_text)

        # Skip very short labels and common stopwords
        if len(label_text) < MIN_PATTERN_LENGTH:
            continue
        if label_text.lower() in _STOPWORDS:
            continue

        pattern_id = encode_pattern_id(info.concept.iri, info.label_type)

        # Create pattern from label tokens
        tokens = label_text.split()
        if len(tokens) == 1:
            pattern = {"label": "FOLIO_CONCEPT", "pattern": label_text, "id": pattern_id}
        else:
            pattern = {
                "label": "FOLIO_CONCEPT",
                "pattern": [{"LOWER": t.lower()} for t in tokens],
                "id": pattern_id,
            }
        patterns.append(pattern)

    return patterns
