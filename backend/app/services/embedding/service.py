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


# Module-level FAISS embedding index singleton
_embedding_index = None


def get_embedding_index():
    """Get the FAISS-backed FOLIO embedding index, or None if not built."""
    return _embedding_index


def build_embedding_index(folio_service) -> None:
    """Build a FAISS-backed embedding index of all FOLIO concepts.

    Uses the configured embedding provider.
    """
    global _embedding_index

    from app.config import settings

    if getattr(settings, "embedding_disabled", False):
        logger.info("Embedding disabled by configuration")
        return

    try:
        from app.services.embedding.folio_index import FOLIOEmbeddingIndex
    except ImportError:
        logger.warning("FAISS not available; embedding index not built")
        return

    provider = _create_embedding_provider()
    if provider is None:
        return

    # Collect concept data from FOLIO
    folio_raw = folio_service._get_folio()
    iri_hashes = []
    labels = []
    definitions = []
    branches = []

    for owl_class in folio_raw.classes:
        iri_hash = owl_class.iri.rsplit("/", 1)[-1]
        label = owl_class.label or iri_hash
        defn = owl_class.definition
        iri_hashes.append(iri_hash)
        labels.append(label)
        definitions.append(defn)
        # Branch detection is expensive; leave empty for now
        branches.append("")

    index = FOLIOEmbeddingIndex(
        provider=provider,
        iri_hashes=iri_hashes,
        labels=labels,
        definitions=definitions,
        branches=branches,
    )
    index.build()
    _embedding_index = index
    logger.info("Built FAISS embedding index with %d concepts", index.num_concepts)


def get_embedding_status() -> dict:
    """Return current embedding system status."""
    from app.config import settings

    faiss_available = False
    try:
        import faiss  # noqa: F401
        faiss_available = True
    except ImportError:
        pass

    index = get_embedding_index()
    return {
        "provider": getattr(settings, "embedding_provider", "local"),
        "model": settings.embedding_model,
        "index_size": index.num_concepts if index else 0,
        "faiss_available": faiss_available,
        "disabled": getattr(settings, "embedding_disabled", False),
    }


def _create_embedding_provider():
    """Create an embedding provider based on configuration."""
    from app.config import settings

    provider_type = getattr(settings, "embedding_provider", "local")

    if provider_type == "ollama":
        try:
            from app.services.embedding.providers.ollama import OllamaEmbeddingProvider
            return OllamaEmbeddingProvider(
                model=settings.embedding_model,
                base_url=getattr(settings, "embedding_base_url", None),
            )
        except Exception:
            logger.warning("Ollama provider failed, falling back to local", exc_info=True)

    if provider_type == "openai":
        try:
            from app.services.embedding.providers.openai import OpenAIEmbeddingProvider
            return OpenAIEmbeddingProvider(
                model=settings.embedding_model,
                api_key=getattr(settings, "embedding_api_key", None),
                base_url=getattr(settings, "embedding_base_url", None),
            )
        except Exception:
            logger.warning("OpenAI embedding provider failed, falling back to local", exc_info=True)

    # Default: local
    from app.services.embedding.providers.local import LocalEmbeddingProvider
    return LocalEmbeddingProvider(model_name=settings.embedding_model)


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
