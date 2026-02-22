from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    label: str
    score: float
    metadata: dict


class EmbeddingService:
    """Singleton embedding service with vector index for similarity search."""

    _instance: EmbeddingService | None = None

    def __init__(self) -> None:
        self._labels: list[str] = []
        self._metadata: list[dict] = []
        self._embeddings: np.ndarray | None = None
        self._provider = None

    @classmethod
    def get_instance(cls) -> EmbeddingService:
        if cls._instance is None:
            cls._instance = EmbeddingService()
        return cls._instance

    def _get_provider(self):
        if self._provider is None:
            from app.services.embedding.providers.local import LocalEmbeddingProvider

            self._provider = LocalEmbeddingProvider()
        return self._provider

    def index_labels(self, labels: list[str], metadata: list[dict] | None = None) -> None:
        provider = self._get_provider()
        self._labels = labels
        self._metadata = metadata or [{} for _ in labels]
        if labels:
            self._embeddings = provider.encode(labels)
            logger.info("Indexed %d labels (%d dims)", len(labels), self._embeddings.shape[1])
        else:
            self._embeddings = None

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if self._embeddings is None or len(self._labels) == 0:
            return []

        provider = self._get_provider()
        query_vec = provider.encode_single(query)

        # Cosine similarity (embeddings are already normalized)
        scores = self._embeddings @ query_vec
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            results.append(
                SearchResult(
                    label=self._labels[idx],
                    score=float(scores[idx]),
                    metadata=self._metadata[idx],
                )
            )
        return results

    def similarity(self, text_a: str, text_b: str) -> float:
        provider = self._get_provider()
        vecs = provider.encode([text_a, text_b])
        return float(np.dot(vecs[0], vecs[1]))

    def index_folio_labels(self, folio_service) -> None:
        """Index all FOLIO concept labels for semantic search."""
        labels_dict = folio_service.get_all_labels()
        labels = list(labels_dict.keys())
        metadata = [
            {
                "iri": info.concept.iri,
                "label": info.matched_label,
                "type": info.label_type,
            }
            for info in labels_dict.values()
        ]
        self.index_labels(labels, metadata)
        logger.info("Indexed %d FOLIO labels into embedding service", len(labels))

    @property
    def index_size(self) -> int:
        return len(self._labels)
