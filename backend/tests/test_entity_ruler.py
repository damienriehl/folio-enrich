import pytest

from app.services.entity_ruler.pattern_builder import build_patterns
from app.services.entity_ruler.ruler import FOLIOEntityRuler
from app.services.folio.folio_service import FOLIOConcept


def _make_concepts() -> dict[str, FOLIOConcept]:
    return {
        "breach of contract": FOLIOConcept(
            iri="iri1", preferred_label="Breach of Contract",
            alternative_labels=[], definition="", branch="Legal Concepts", parent_iris=[],
        ),
        "damages": FOLIOConcept(
            iri="iri2", preferred_label="Damages",
            alternative_labels=[], definition="", branch="Legal Concepts", parent_iris=[],
        ),
        "motion to dismiss": FOLIOConcept(
            iri="iri3", preferred_label="Motion to Dismiss",
            alternative_labels=[], definition="", branch="Legal Processes", parent_iris=[],
        ),
        "court": FOLIOConcept(
            iri="iri4", preferred_label="Court",
            alternative_labels=[], definition="", branch="Legal Entities", parent_iris=[],
        ),
    }


class TestPatternBuilder:
    def test_builds_patterns(self):
        concepts = _make_concepts()
        patterns = build_patterns(concepts)
        assert len(patterns) == 4

    def test_single_token_pattern(self):
        concepts = {"court": FOLIOConcept(
            iri="iri1", preferred_label="Court",
            alternative_labels=[], definition="", branch="", parent_iris=[],
        )}
        patterns = build_patterns(concepts)
        assert len(patterns) == 1
        # Single-word pattern is a string
        assert patterns[0]["pattern"] == "court"

    def test_multi_token_pattern(self):
        concepts = {"breach of contract": FOLIOConcept(
            iri="iri1", preferred_label="Breach of Contract",
            alternative_labels=[], definition="", branch="", parent_iris=[],
        )}
        patterns = build_patterns(concepts)
        assert len(patterns) == 1
        # Multi-word pattern is list of token dicts
        assert isinstance(patterns[0]["pattern"], list)
        assert len(patterns[0]["pattern"]) == 3


class TestFOLIOEntityRuler:
    def test_find_matches(self):
        ruler = FOLIOEntityRuler()
        ruler.load_patterns(_make_concepts())
        matches = ruler.find_matches("The court granted the motion to dismiss.")
        texts = {m.text.lower() for m in matches}
        assert "court" in texts
        assert "motion to dismiss" in texts

    def test_match_offsets(self):
        ruler = FOLIOEntityRuler()
        ruler.load_patterns(_make_concepts())
        text = "The court ruled."
        matches = ruler.find_matches(text)
        assert len(matches) >= 1
        court_match = [m for m in matches if m.text.lower() == "court"][0]
        assert text[court_match.start_char:court_match.end_char].lower() == "court"

    def test_no_patterns_returns_empty(self):
        ruler = FOLIOEntityRuler()
        matches = ruler.find_matches("The court ruled.")
        assert len(matches) == 0

    def test_case_insensitive(self):
        ruler = FOLIOEntityRuler()
        ruler.load_patterns(_make_concepts())
        matches = ruler.find_matches("The COURT granted DAMAGES.")
        texts = {m.text.lower() for m in matches}
        assert "court" in texts
        assert "damages" in texts
