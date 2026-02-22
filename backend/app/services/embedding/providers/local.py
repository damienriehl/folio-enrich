from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider:
    """Local embedding provider using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
                logger.info("Loaded embedding model: %s", self.model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for local embeddings. "
                    "Install with: pip install sentence-transformers"
                )
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._get_model()
        return model.encode(texts, normalize_embeddings=True)

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    @property
    def dimension(self) -> int:
        return 384  # MiniLM-L6-v2 default
