"""Abstract base class for embedding providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BaseEmbeddingProvider(ABC):
    """Interface for embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns a 1-D normalized vector."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts. Returns (N, dim) normalized array."""

    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        """L2-normalize vectors for cosine similarity via inner product."""
        norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return vectors / norms
