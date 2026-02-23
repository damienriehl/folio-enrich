"""Ollama embedding provider for users running Ollama locally."""

from __future__ import annotations

import logging

import httpx
import numpy as np

from app.services.embedding.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "nomic-embed-text"
_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """Embedding provider using Ollama's /api/embed endpoint."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._model_name = model or _DEFAULT_MODEL
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._dim: int | None = None

        # Probe dimension with a test embedding
        test_vec = self.embed("test")
        self._dim = len(test_vec)
        logger.info("Ollama provider ready: %s (dim=%d)", self._model_name, self._dim)

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Call Ollama embed API."""
        resp = httpx.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model_name, "input": texts},
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"]

    def embed(self, text: str) -> np.ndarray:
        embeddings = self._request_embeddings([text])
        vec = np.asarray(embeddings[0], dtype=np.float32)
        return self._normalize(vec.reshape(1, -1)).flatten()

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        all_vecs = []
        batch_size = 64
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self._request_embeddings(batch)
            all_vecs.extend(embeddings)
        arr = np.asarray(all_vecs, dtype=np.float32)
        return self._normalize(arr)

    def dimension(self) -> int:
        if self._dim is None:
            raise RuntimeError("Dimension not yet determined")
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name
