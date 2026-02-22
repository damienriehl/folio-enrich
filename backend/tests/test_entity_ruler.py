import pytest

from app.services.entity_ruler.pattern_builder import build_patterns, decode_pattern_id
from app.services.entity_ruler.ruler import FOLIOEntityRuler
from app.services.folio.folio_service import FOLIOConcept, LabelInfo


def _make_concept(iri, label, branch="Legal Concepts"):
    return FOLIOConcept(
        iri=iri, preferred_label=label,
        alternative_labels=[], definition="", branch=branch, parent_iris=[],
    )


def _make_labels() -> dict[str, LabelInfo]:
    return {
        "breach of contract": LabelInfo(
            concept=_make_concept("iri1", "Breach of Contract"),
            label_type="preferred", matched_label="Breach of Contract",
        ),
        "damages": LabelInfo(
            concept=_make_concept("iri2", "Damages"),
            label_type="preferred", matched_label="Damages",
        ),
        "motion to dismiss": LabelInfo(
            concept=_make_concept("iri3", "Motion to Dismiss", "Legal Processes"),
            label_type="preferred", matched_label="Motion to Dismiss",
        ),
        "court": LabelInfo(
            concept=_make_concept("iri4", "Court", "Legal Entities"),
            label_type="preferred", matched_label="Court",
        ),
    }


class TestPatternBuilder:
    def test_builds_patterns(self):
        labels = _make_labels()
        patterns = build_patterns(labels)
        assert len(patterns) == 4

    def test_single_token_pattern(self):
        labels = {"court": LabelInfo(
            concept=_make_concept("iri1", "Court"),
            label_type="preferred", matched_label="Court",
        )}
        patterns = build_patterns(labels)
        assert len(patterns) == 1
        # Single-word pattern is a string
        assert patterns[0]["pattern"] == "court"

    def test_multi_token_pattern(self):
        labels = {"breach of contract": LabelInfo(
            concept=_make_concept("iri1", "Breach of Contract"),
            label_type="preferred", matched_label="Breach of Contract",
        )}
        patterns = build_patterns(labels)
        assert len(patterns) == 1
        # Multi-word pattern is list of token dicts
        assert isinstance(patterns[0]["pattern"], list)
        assert len(patterns[0]["pattern"]) == 3

    def test_pattern_id_encodes_label_type(self):
        labels = {
            "court": LabelInfo(
                concept=_make_concept("iri1", "Court"),
                label_type="preferred", matched_label="Court",
            ),
            "grant": LabelInfo(
                concept=_make_concept("iri2", "Donation"),
                label_type="alternative", matched_label="Grant",
            ),
        }
        patterns = build_patterns(labels)
        assert len(patterns) == 2
        ids = {p["pattern"] if isinstance(p["pattern"], str) else None: p["id"] for p in patterns}
        court_id = ids.get("court")
        grant_id = ids.get("grant")
        assert court_id is not None
        assert grant_id is not None
        iri1, type1 = decode_pattern_id(court_id)
        assert iri1 == "iri1"
        assert type1 == "preferred"
        iri2, type2 = decode_pattern_id(grant_id)
        assert iri2 == "iri2"
        assert type2 == "alternative"


class TestFOLIOEntityRuler:
    def test_find_matches(self):
        ruler = FOLIOEntityRuler()
        ruler.load_patterns(_make_labels())
        matches = ruler.find_matches("The court granted the motion to dismiss.")
        texts = {m.text.lower() for m in matches}
        assert "court" in texts
        assert "motion to dismiss" in texts

    def test_match_has_match_type(self):
        labels = {
            "court": LabelInfo(
                concept=_make_concept("iri1", "Court"),
                label_type="preferred", matched_label="Court",
            ),
            "grant": LabelInfo(
                concept=_make_concept("iri2", "Donation"),
                label_type="alternative", matched_label="Grant",
            ),
        }
        ruler = FOLIOEntityRuler()
        ruler.load_patterns(labels)
        matches = ruler.find_matches("The court granted a grant.")
        for m in matches:
            if m.text.lower() == "court":
                assert m.match_type == "preferred"
                assert m.entity_id == "iri1"
            elif m.text.lower() == "grant":
                assert m.match_type == "alternative"
                assert m.entity_id == "iri2"

    def test_match_offsets(self):
        ruler = FOLIOEntityRuler()
        ruler.load_patterns(_make_labels())
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
        ruler.load_patterns(_make_labels())
        matches = ruler.find_matches("The COURT granted DAMAGES.")
        texts = {m.text.lower() for m in matches}
        assert "court" in texts
        assert "damages" in texts
