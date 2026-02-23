"""OpenAI embedding provider."""

from __future__ import annotations

import logging

import numpy as np
from openai import OpenAI

from app.services.embedding.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "text-embedding-3-small"

# Known dimensions for OpenAI models
_MODEL_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Embedding provider using OpenAI's embeddings API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self._model_name = model or _DEFAULT_MODEL
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._dim = _MODEL_DIMS.get(self._model_name)

        # Probe dimension if unknown model
        if self._dim is None:
            test_vec = self.embed("test")
            self._dim = len(test_vec)

        logger.info("OpenAI provider ready: %s (dim=%d)", self._model_name, self._dim)

    def embed(self, text: str) -> np.ndarray:
        resp = self._client.embeddings.create(
            model=self._model_name,
            input=text,
        )
        vec = np.asarray(resp.data[0].embedding, dtype=np.float32)
        return self._normalize(vec.reshape(1, -1)).flatten()

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        all_vecs = []
        batch_size = 2048
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self._client.embeddings.create(
                model=self._model_name,
                input=batch,
            )
            sorted_data = sorted(resp.data, key=lambda d: d.index)
            all_vecs.extend([d.embedding for d in sorted_data])
        arr = np.asarray(all_vecs, dtype=np.float32)
        return self._normalize(arr)

    def dimension(self) -> int:
        if self._dim is None:
            raise RuntimeError("Dimension not yet determined")
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name
