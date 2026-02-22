from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticMatch:
    text: str
    start: int
    end: int
    matched_label: str
    similarity: float
    iri: str


class SemanticEntityRuler:
    """Embedding-enhanced EntityRuler for near-match discovery."""

    def __init__(self, embedding_service=None, threshold: float = 0.80) -> None:
        self._embedding_service = embedding_service
        self.threshold = threshold

    def find_semantic_matches(
        self, text: str, known_spans: set[tuple[int, int]]
    ) -> list[SemanticMatch]:
        """Find concept mentions missed by exact-match ruler using embedding similarity.

        known_spans: set of (start, end) already matched by EntityRuler/Aho-Corasick
        """
        if self._embedding_service is None or self._embedding_service.index_size == 0:
            return []

        # Extract candidate phrases (2-4 word n-grams)
        words = text.split()
        matches = []

        for n in range(2, 5):
            pos = 0
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i : i + n])
                # Find start position in original text
                start = text.find(phrase, pos)
                if start == -1:
                    continue
                end = start + len(phrase)
                pos = start + 1

                # Skip if already matched
                if any(
                    s <= start < e or s < end <= e
                    for s, e in known_spans
                ):
                    continue

                # Search embeddings
                results = self._embedding_service.search(phrase, top_k=1)
                if results and results[0].score >= self.threshold:
                    matches.append(SemanticMatch(
                        text=phrase,
                        start=start,
                        end=end,
                        matched_label=results[0].label,
                        similarity=results[0].score,
                        iri=results[0].metadata.get("iri", ""),
                    ))

        return matches
