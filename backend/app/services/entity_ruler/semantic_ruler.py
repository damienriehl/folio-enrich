from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.entity_ruler.pattern_builder import _STOPWORDS

logger = logging.getLogger(__name__)

# Extended stopwords for semantic matching — superset of pattern_builder._STOPWORDS.
# Includes common function words that are legitimate exact-match patterns (e.g. "will",
# "shall") but should never anchor a semantic embedding search.
_SEMANTIC_STOPWORDS = _STOPWORDS | frozenset({
    # Pronouns / determiners
    "this", "that", "they", "them", "what", "when", "where", "which",
    "whom", "each", "some", "such", "both", "same", "said", "here",
    # Auxiliary / common verbs
    "have", "been", "were", "will", "does", "done", "made", "shall",
    "being",
    # Prepositions / conjunctions / adverbs
    "with", "from", "into", "than", "then", "also", "just", "even",
    "more", "most", "only", "over", "very", "well", "much", "back",
    "like", "upon", "thus", "once",
})


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

        # Phase 1: Collect all candidate n-grams, filtering known spans
        words = text.split()
        candidates = []  # (phrase, start, end)

        for n in range(2, 5):
            pos = 0
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i : i + n])
                start = text.find(phrase, pos)
                if start == -1:
                    continue
                end = start + len(phrase)
                pos = start + 1

                if any(
                    s <= start < e or s < end <= e
                    for s, e in known_spans
                ):
                    continue

                # Skip candidates where every token is a common stopword
                tokens = phrase.lower().split()
                if all(t in _SEMANTIC_STOPWORDS for t in tokens):
                    continue

                candidates.append((phrase, start, end))

        if not candidates:
            return []

        # Phase 2: Batch embed all candidates in a single forward pass
        phrases = [c[0] for c in candidates]
        batch_results = self._embedding_service.search_batch(phrases, top_k=1)

        # Phase 3: Filter by threshold
        matches = []
        for (phrase, start, end), results in zip(candidates, batch_results):
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
