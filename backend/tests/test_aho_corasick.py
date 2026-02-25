import pytest

from app.services.matching.aho_corasick import AhoCorasickMatcher


class TestAhoCorasickMatcher:
    def test_basic_search(self):
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("breach of contract", {"iri": "iri1"})
        matcher.add_pattern("damages", {"iri": "iri2"})
        matcher.build()

        results = matcher.search("The breach of contract resulted in damages to the plaintiff.")
        assert len(results) == 2
        assert results[0].pattern == "breach of contract"
        assert results[0].value == {"iri": "iri1"}
        assert results[1].pattern == "damages"

    def test_case_insensitive(self):
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("Motion to Dismiss", {"iri": "iri1"})
        matcher.build()

        results = matcher.search("The motion to dismiss was granted.")
        assert len(results) == 1
        assert results[0].pattern == "Motion to Dismiss"

    def test_word_boundary_check(self):
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("contract", {"iri": "iri1"})
        matcher.build()

        # Should NOT match "contractual" — no word boundary at end
        results = matcher.search("The contractual obligation was clear.")
        assert len(results) == 0

        # Should match standalone "contract"
        results = matcher.search("The contract was signed.")
        assert len(results) == 1

    def test_contained_spans_both_kept(self):
        """Contained spans should both survive (breach inside breach of contract)."""
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("breach", {"iri": "short"})
        matcher.add_pattern("breach of contract", {"iri": "long"})
        matcher.build()

        results = matcher.search("The breach of contract was evident.")
        assert len(results) == 2
        patterns = {r.pattern for r in results}
        assert "breach of contract" in patterns
        assert "breach" in patterns

    def test_multiple_occurrences(self):
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("damages", {"iri": "iri1"})
        matcher.build()

        results = matcher.search("The damages were severe. Additional damages were found.")
        assert len(results) == 2

    def test_no_matches(self):
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("habeas corpus", {})
        matcher.build()

        results = matcher.search("This text has no legal terms.")
        assert len(results) == 0

    def test_correct_offsets(self):
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("court", {})
        matcher.build()

        text = "The court ruled."
        results = matcher.search(text)
        assert len(results) == 1
        assert results[0].start == 4
        assert results[0].end == 9
        assert text[results[0].start : results[0].end] == "court"

    def test_add_patterns_bulk(self):
        matcher = AhoCorasickMatcher()
        matcher.add_patterns({
            "tort": {"iri": "1"},
            "negligence": {"iri": "2"},
            "duty of care": {"iri": "3"},
        })
        matcher.build()
        assert matcher.pattern_count == 3

    def test_partial_overlap_longer_wins(self):
        """Partial overlaps (crossing boundaries) should resolve to the longer match."""
        matcher = AhoCorasickMatcher()
        # These would partially overlap if they both appeared at overlapping positions
        matcher.add_pattern("new york", {"iri": "ny"})
        matcher.add_pattern("york county", {"iri": "yc"})
        matcher.build()

        # "new york county" — "new york" starts at 4, "york county" starts at 8
        # These partially overlap (york is shared), so longer one wins or first
        results = matcher.search("The new york county case.")
        # Both patterns match at different positions but overlap on "york"
        # new york = (4,12), york county = (8,20) — partial overlap → one wins
        assert len(results) == 1

    def test_identical_spans_deduplicated(self):
        """Identical spans should be deduplicated."""
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("contract", {"iri": "1"})
        matcher.build()

        results = matcher.search("The contract was signed.")
        assert len(results) == 1

    def test_contained_inner_span_kept(self):
        """Inner span fully contained within outer span should be kept."""
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("contract", {"iri": "inner"})
        matcher.add_pattern("breach of contract", {"iri": "outer"})
        matcher.build()

        results = matcher.search("The breach of contract was clear.")
        assert len(results) == 2
        iris = {r.value["iri"] for r in results}
        assert "inner" in iris
        assert "outer" in iris
        # Outer span should come first (earlier start)
        assert results[0].pattern == "breach of contract"
        assert results[1].pattern == "contract"

    def test_auto_build_on_search(self):
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("test", {})
        # Don't call build() — should auto-build
        results = matcher.search("This is a test.")
        assert len(results) == 1
