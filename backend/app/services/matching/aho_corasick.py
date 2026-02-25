from __future__ import annotations

import logging
from dataclasses import dataclass

import ahocorasick

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    pattern: str
    start: int
    end: int
    value: dict  # associated metadata (e.g., FOLIO IRI, label)


def _is_word_boundary(text: str, pos: int) -> bool:
    """Check if position is at a word boundary using character-class check."""
    if pos < 0 or pos >= len(text):
        return True
    ch = text[pos]
    return not (ch.isalnum() or ch == "_")


class AhoCorasickMatcher:
    """Multi-pattern string matcher using Aho-Corasick automaton."""

    def __init__(self) -> None:
        self._automaton = ahocorasick.Automaton()
        self._built = False

    def add_pattern(self, pattern: str, value: dict | None = None) -> None:
        """Add a pattern to match. Value is metadata attached to matches."""
        key = pattern.lower()
        self._automaton.add_word(key, (pattern, value or {}))
        self._built = False

    def add_patterns(self, patterns: dict[str, dict]) -> None:
        """Add multiple patterns at once. Keys are patterns, values are metadata."""
        for pattern, value in patterns.items():
            self.add_pattern(pattern, value)

    def build(self) -> None:
        """Build the automaton. Must be called after adding all patterns."""
        self._automaton.make_automaton()
        self._built = True

    def search(self, text: str, case_sensitive: bool = False) -> list[MatchResult]:
        if not self._built:
            self.build()

        search_text = text if case_sensitive else text.lower()
        raw_matches: list[MatchResult] = []

        for end_idx, (pattern, value) in self._automaton.iter(search_text):
            start_idx = end_idx - len(pattern) + 1
            # Word-boundary validation
            if not _is_word_boundary(search_text, start_idx - 1):
                continue
            if not _is_word_boundary(search_text, end_idx + 1):
                continue

            raw_matches.append(
                MatchResult(
                    pattern=pattern,
                    start=start_idx,
                    end=end_idx + 1,  # exclusive end
                    value=value,
                )
            )

        return self._resolve_overlaps(raw_matches)

    def _resolve_overlaps(self, matches: list[MatchResult]) -> list[MatchResult]:
        """Resolve overlapping spans with containment awareness.

        - Contained spans (A fully inside B): keep both
        - Partial overlaps (spans cross boundaries): longer wins
        - Identical spans: keep first
        """
        if not matches:
            return []

        # Sort by start asc, length desc (longer spans first at same start)
        matches.sort(key=lambda m: (m.start, -(m.end - m.start)))

        resolved: list[MatchResult] = []

        for match in matches:
            dominated = False
            for i, kept in enumerate(resolved):
                # Check if spans overlap at all
                if match.start >= kept.end or match.end <= kept.start:
                    continue  # no overlap

                # Identical span — skip duplicate
                if match.start == kept.start and match.end == kept.end:
                    dominated = True
                    break

                # Check containment: match is fully inside kept
                if match.start >= kept.start and match.end <= kept.end:
                    # Contained — allow it (both survive)
                    continue

                # Check containment: kept is fully inside match
                if kept.start >= match.start and kept.end <= match.end:
                    # Match contains kept — allow it (both survive)
                    continue

                # Partial overlap — longer wins
                match_len = match.end - match.start
                kept_len = kept.end - kept.start
                if match_len > kept_len:
                    resolved[i] = match
                    dominated = True
                    break
                else:
                    dominated = True
                    break

            if not dominated:
                resolved.append(match)

        # Sort results by start position for stable output
        resolved.sort(key=lambda m: (m.start, -(m.end - m.start)))
        return resolved

    @property
    def pattern_count(self) -> int:
        return len(self._automaton)
