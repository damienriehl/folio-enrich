"""FAISS index of FOLIO concept embeddings with disk caching."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np

from app.services.embedding.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".folio-enrich" / "cache" / "embeddings"


class FOLIOEmbeddingIndex:
    """Embeds all FOLIO concepts and indexes them with FAISS for fast similarity search.

    Each concept is embedded as "label: definition" (or just "label" if no definition).
    The index uses cosine similarity via IndexFlatIP on L2-normalized vectors.
    Results can be filtered by branch at query time.
    """

    def __init__(
        self,
        provider: BaseEmbeddingProvider,
        iri_hashes: list[str],
        labels: list[str],
        definitions: list[str | None],
        branches: list[str],
    ):
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "faiss-cpu is required for embedding search. "
                "Install with: pip install faiss-cpu"
            )

        self._provider = provider
        self._iri_hashes = iri_hashes
        self._labels = labels
        self._definitions = definitions
        self._branches = branches
        self._faiss = faiss

        # Build branch -> index set for fast filtering
        self._branch_indices: dict[str, list[int]] = {}
        for i, branch in enumerate(branches):
            self._branch_indices.setdefault(branch, []).append(i)

        self._index: object | None = None
        self._vectors: np.ndarray | None = None

    @property
    def num_concepts(self) -> int:
        return len(self._iri_hashes)

    def _build_texts(self) -> list[str]:
        """Build embedding texts: 'label: definition' or just 'label'."""
        texts = []
        for label, defn in zip(self._labels, self._definitions):
            if defn:
                texts.append(f"{label}: {defn}")
            else:
                texts.append(label)
        return texts

    def _cache_path(self, owl_hash: str) -> Path:
        """Cache path: ~/.folio-enrich/cache/embeddings/{model}_{owl_hash}.pkl"""
        model_slug = self._provider.model_name.replace("/", "_").replace("\\", "_")
        return _CACHE_DIR / f"{model_slug}_{owl_hash}.pkl"

    def build(self, owl_hash: str | None = None) -> None:
        """Build the FAISS index, using disk cache if available."""
        # Try loading from cache
        if owl_hash:
            cache_file = self._cache_path(owl_hash)
            if cache_file.exists():
                try:
                    self._load_cache(cache_file)
                    logger.info(
                        "Loaded embedding index from cache: %s (%d concepts)",
                        cache_file.name, len(self._iri_hashes),
                    )
                    return
                except Exception as e:
                    logger.warning("Cache load failed, rebuilding: %s", e)

        # Build fresh embeddings
        texts = self._build_texts()
        logger.info("Embedding %d FOLIO concepts with %s...", len(texts), self._provider.model_name)
        self._vectors = self._provider.embed_batch(texts)

        # Build FAISS index
        dim = self._provider.dimension()
        self._index = self._faiss.IndexFlatIP(dim)
        self._index.add(self._vectors)
        logger.info("FAISS index built: %d vectors, dim=%d", self._index.ntotal, dim)

        # Save to cache
        if owl_hash:
            try:
                self._save_cache(self._cache_path(owl_hash))
            except Exception as e:
                logger.warning("Failed to save embedding cache: %s", e)

    def _save_cache(self, path: Path) -> None:
        """Serialize vectors + metadata to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "vectors": self._vectors,
            "iri_hashes": self._iri_hashes,
            "labels": self._labels,
            "definitions": self._definitions,
            "branches": self._branches,
            "model": self._provider.model_name,
            "dim": self._provider.dimension(),
        }
        with open(path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("Saved embedding cache: %s", path.name)

    def _load_cache(self, path: Path) -> None:
        """Load vectors from disk cache and rebuild FAISS index."""
        with open(path, "rb") as f:
            data = pickle.load(f)  # noqa: S301 -- trusted local cache

        if data["model"] != self._provider.model_name:
            raise ValueError(f"Model mismatch: cache={data['model']}, current={self._provider.model_name}")
        if data["dim"] != self._provider.dimension():
            raise ValueError(f"Dimension mismatch: cache={data['dim']}, current={self._provider.dimension()}")
        if len(data["iri_hashes"]) != len(self._iri_hashes):
            raise ValueError(
                f"Concept count mismatch: cache={len(data['iri_hashes'])}, current={len(self._iri_hashes)}"
            )

        self._vectors = data["vectors"]
        self._index = self._faiss.IndexFlatIP(data["dim"])
        self._index.add(self._vectors)

    def query(
        self,
        text: str,
        top_k: int = 20,
        branch_filter: set[str] | None = None,
    ) -> list[tuple[str, str, float]]:
        """Query the index for similar concepts.

        Returns list of (iri_hash, label, score) tuples sorted by score desc.
        """
        if self._index is None:
            raise RuntimeError("Index not built. Call build() first.")

        query_vec = self._provider.embed(text).reshape(1, -1)

        if branch_filter:
            search_k = min(top_k * 5, self._index.ntotal)
            scores, indices = self._index.search(query_vec, search_k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:
                    continue
                if self._branches[idx] in branch_filter:
                    results.append((
                        self._iri_hashes[idx],
                        self._labels[idx],
                        float(score),
                    ))
                    if len(results) >= top_k:
                        break
            return results
        else:
            search_k = min(top_k, self._index.ntotal)
            scores, indices = self._index.search(query_vec, search_k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:
                    continue
                results.append((
                    self._iri_hashes[idx],
                    self._labels[idx],
                    float(score),
                ))
            return results

    def score_candidates(
        self,
        text: str,
        candidate_iri_hashes: list[str],
    ) -> dict[str, float]:
        """Score specific candidates against query text.

        Returns dict of iri_hash -> cosine similarity score.
        """
        if self._index is None or self._vectors is None:
            return {}

        query_vec = self._provider.embed(text).reshape(1, -1)
        hash_to_idx = {h: i for i, h in enumerate(self._iri_hashes)}

        scores = {}
        for h in candidate_iri_hashes:
            idx = hash_to_idx.get(h)
            if idx is not None:
                sim = float(np.dot(query_vec[0], self._vectors[idx]))
                scores[h] = sim

        return scores
