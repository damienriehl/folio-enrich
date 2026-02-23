from __future__ import annotations

import logging

import numpy as np

from app.services.embedding.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    """Local embedding provider using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None
        self._dim = 384  # MiniLM-L6-v2 default

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self._model_name)
                logger.info("Loaded embedding model: %s", self._model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for local embeddings. "
                    "Install with: pip install sentence-transformers"
                )
        return self._model

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns a 1-D normalized vector."""
        return self.encode([text])[0]

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts. Returns (N, dim) normalized array."""
        return self.encode(texts)

    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    # Legacy API for backward compatibility
    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._get_model()
        return model.encode(texts, normalize_embeddings=True)

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]
