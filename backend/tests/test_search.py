"""Tests for multi-strategy search module."""

import pytest

from app.services.folio.search import (
    _compute_relevance_score,
    _content_words,
    _generate_search_terms,
    _tokenize,
    _word_overlap,
    multi_strategy_search,
)


class TestTokenize:
    def test_basic(self):
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_single_char_excluded(self):
        assert _tokenize("a b cd") == ["cd"]

    def test_non_alpha_stripped(self):
        tokens = _tokenize("LLC/Corp (2024)")
        assert "llc" in tokens
        assert "corp" in tokens
        assert "2024" not in tokens  # numbers are excluded


class TestContentWords:
    def test_removes_stopwords(self):
        words = _content_words("the law of the land")
        assert "the" not in words
        assert "of" not in words
        assert "land" in words

    def test_removes_domain_stopwords(self):
        words = _content_words("general legal types")
        assert len(words) == 0  # all are stopwords


class TestWordOverlap:
    def test_exact_match_gives_1(self):
        score = _word_overlap({"contract"}, {"contract"})
        assert score == 1.0

    def test_no_overlap_gives_0(self):
        score = _word_overlap({"apple"}, {"banana"})
        assert score == 0.0

    def test_empty_sets(self):
        assert _word_overlap(set(), {"hello"}) == 0.0
        assert _word_overlap({"hello"}, set()) == 0.0

    def test_partial_overlap(self):
        score = _word_overlap({"breach", "contract"}, {"contract", "law"})
        assert 0.3 < score < 0.8

    def test_prefix_match_credit(self):
        score = _word_overlap({"litigation"}, {"litigat"})
        assert score >= 0.7

    def test_morphological_stem_credit(self):
        # "defense" and "defendant" share "defen" prefix (5 chars)
        score = _word_overlap({"defense"}, {"defendant"})
        assert score >= 0.6

    def test_reverse_overlap_for_multi_word_targets(self):
        # Target "business law" has 2 words, both in query
        score = _word_overlap(
            {"small", "business", "formation"},
            {"business", "law"},
        )
        # Reverse overlap: both of target's words covered
        assert score > 0.3


class TestComputeRelevanceScore:
    def test_exact_match_returns_99(self):
        score = _compute_relevance_score(
            {"breach", "contract"}, "Breach of Contract",
            "Breach of Contract", None, [],
        )
        assert score == 99.0

    def test_query_in_label_returns_92(self):
        score = _compute_relevance_score(
            {"dog", "bite"}, "Dog Bite",
            "Dog Bite Strict Liability", None, [],
        )
        assert score >= 92.0

    def test_label_in_query_returns_88(self):
        score = _compute_relevance_score(
            {"criminal", "defense", "attorney"}, "criminal defense attorney",
            "Criminal Defense", None, [],
        )
        assert score >= 88.0

    def test_word_overlap_scoring(self):
        score = _compute_relevance_score(
            {"employment", "discrimination"}, "employment discrimination",
            "Workplace Discrimination Law", None, [],
        )
        assert score > 30.0

    def test_synonym_scoring(self):
        score = _compute_relevance_score(
            {"tribunal"}, "tribunal",
            "Court", None, ["Tribunal", "Judicial Body"],
        )
        assert score > 50.0

    def test_definition_scoring(self):
        score = _compute_relevance_score(
            {"bankruptcy"}, "bankruptcy",
            "Insolvency Law", "Deals with bankruptcy proceedings", [],
        )
        assert score > 30.0

    def test_empty_label_returns_0(self):
        score = _compute_relevance_score(
            {"test"}, "test", "", None, [],
        )
        assert score == 0.0

    def test_score_capped_at_99(self):
        score = _compute_relevance_score(
            {"test"}, "test", "test", "test test test", ["test"],
        )
        assert score <= 99.0


class TestGenerateSearchTerms:
    def test_full_phrase_always_first(self):
        terms = _generate_search_terms("breach of contract")
        assert terms[0] == "breach of contract"

    def test_sub_phrases_generated(self):
        terms = _generate_search_terms("small business formation")
        # Should include 2-word sub-phrases
        lower_terms = [t.lower() for t in terms]
        assert "small business" in lower_terms
        assert "business formation" in lower_terms

    def test_content_words_included(self):
        terms = _generate_search_terms("the law of contracts")
        lower_terms = [t.lower() for t in terms]
        assert "contracts" in lower_terms

    def test_legal_expansions(self):
        terms = _generate_search_terms("litigation")
        lower_terms = [t.lower() for t in terms]
        assert "litigation practice" in lower_terms
        assert "litigation service" in lower_terms

    def test_deduplication(self):
        terms = _generate_search_terms("litigation practice")
        lower_terms = [t.lower() for t in terms]
        # Count occurrences — should be no duplicates
        assert len(lower_terms) == len(set(lower_terms))

    def test_single_word(self):
        terms = _generate_search_terms("bankruptcy")
        assert len(terms) >= 1
        assert terms[0] == "bankruptcy"


class FakeOWLClass:
    """Minimal mock of an OWL class from folio-python."""
    def __init__(self, iri, label, definition=None, alt_labels=None, sub_class_of=None):
        self.iri = iri
        self.label = label
        self.definition = definition
        self.alternative_labels = alt_labels or []
        self.sub_class_of = sub_class_of or []


class FakeFOLIO:
    """Minimal mock of folio-python's FOLIO class."""
    def __init__(self, concepts: list[FakeOWLClass]):
        self._by_hash = {}
        for c in concepts:
            h = c.iri.rsplit("/", 1)[-1]
            self._by_hash[h] = c

    def __getitem__(self, key):
        return self._by_hash.get(key)

    def search_by_label(self, text, include_alt_labels=True, limit=25):
        text_lower = text.lower()
        results = []
        for c in self._by_hash.values():
            if text_lower in (c.label or "").lower():
                results.append((c, 0.9))
            elif any(text_lower in alt.lower() for alt in c.alternative_labels):
                results.append((c, 0.7))
        return results[:limit]

    def search_by_prefix(self, prefix):
        prefix_lower = prefix.lower()
        return [
            c for c in self._by_hash.values()
            if (c.label or "").lower().startswith(prefix_lower)
        ]

    def search_by_definition(self, text, limit=20):
        text_lower = text.lower()
        results = []
        for c in self._by_hash.values():
            if c.definition and text_lower in c.definition.lower():
                results.append((c, 0.5))
        return results[:limit]


class TestMultiStrategySearch:
    @pytest.fixture
    def mock_folio(self):
        return FakeFOLIO([
            FakeOWLClass(
                iri="https://folio.openlegalstandard.org/HASH001",
                label="Breach of Contract",
                definition="Failure to perform contractual obligations",
                alt_labels=["contract breach"],
            ),
            FakeOWLClass(
                iri="https://folio.openlegalstandard.org/HASH002",
                label="Criminal Law",
                definition="Body of law relating to crime",
                alt_labels=["penal law"],
            ),
            FakeOWLClass(
                iri="https://folio.openlegalstandard.org/HASH003",
                label="Employment Discrimination",
                definition="Discrimination in the workplace based on protected characteristics",
            ),
            FakeOWLClass(
                iri="https://folio.openlegalstandard.org/HASH004",
                label="Litigation Practice",
                definition="Practice of conducting lawsuits",
            ),
        ])

    def test_exact_match_returns_high_score(self, mock_folio):
        results = multi_strategy_search(mock_folio, "Breach of Contract", top_n=5)
        assert len(results) > 0
        assert results[0]["iri_hash"] == "HASH001"
        assert results[0]["score"] == 99.0

    def test_returns_dicts_with_expected_keys(self, mock_folio):
        results = multi_strategy_search(mock_folio, "criminal", top_n=5)
        if results:
            r = results[0]
            assert "label" in r
            assert "iri" in r
            assert "iri_hash" in r
            assert "score" in r
            assert "definition" in r
            assert "synonyms" in r

    def test_no_results_for_unrelated_query(self, mock_folio):
        results = multi_strategy_search(mock_folio, "quantum physics", top_n=5)
        # May still find something via broad search, but scores should be low
        high_scoring = [r for r in results if r["score"] >= 50]
        assert len(high_scoring) == 0

    def test_respects_top_n(self, mock_folio):
        results = multi_strategy_search(mock_folio, "law", top_n=2)
        assert len(results) <= 2

    def test_legal_expansion_finds_practice(self, mock_folio):
        results = multi_strategy_search(mock_folio, "litigation", top_n=5)
        labels = [r["label"] for r in results]
        assert "Litigation Practice" in labels
