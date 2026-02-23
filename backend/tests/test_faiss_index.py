"""Tests for FAISS-backed FOLIO embedding index."""

import numpy as np
import pytest

from app.services.embedding.base import BaseEmbeddingProvider


class FakeEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic fake embedding provider for testing."""

    def __init__(self, dim: int = 8):
        self._dim = dim
        self._call_count = 0

    def embed(self, text: str) -> np.ndarray:
        """Produce a deterministic vector based on text hash."""
        rng = np.random.RandomState(hash(text) % (2**31))
        vec = rng.randn(self._dim).astype(np.float32)
        return self._normalize(vec.reshape(1, -1)).flatten()

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        vecs = np.array([self.embed(t) for t in texts], dtype=np.float32)
        return vecs

    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return "fake-test-model"


class TestFOLIOEmbeddingIndex:
    @pytest.fixture
    def sample_index(self):
        from app.services.embedding.folio_index import FOLIOEmbeddingIndex

        provider = FakeEmbeddingProvider(dim=8)
        index = FOLIOEmbeddingIndex(
            provider=provider,
            iri_hashes=["H001", "H002", "H003", "H004"],
            labels=["Breach of Contract", "Criminal Law", "Employment", "Tax Law"],
            definitions=[
                "Failure to perform obligations",
                "Law relating to crime",
                "Work-related law",
                None,
            ],
            branches=["Area of Law", "Area of Law", "Service", "Area of Law"],
        )
        index.build()
        return index

    def test_build_creates_index(self, sample_index):
        assert sample_index._index is not None
        assert sample_index._index.ntotal == 4
        assert sample_index.num_concepts == 4

    def test_query_returns_results(self, sample_index):
        results = sample_index.query("contract breach", top_k=3)
        assert len(results) <= 3
        assert all(len(r) == 3 for r in results)  # (iri_hash, label, score)
        # Scores should be floats
        assert all(isinstance(r[2], float) for r in results)

    def test_query_with_branch_filter(self, sample_index):
        results = sample_index.query(
            "law", top_k=10,
            branch_filter={"Service"},
        )
        # Only "Employment" is in Service branch
        assert all(r[0] == "H003" for r in results)

    def test_score_candidates(self, sample_index):
        scores = sample_index.score_candidates(
            "contract law",
            candidate_iri_hashes=["H001", "H002"],
        )
        assert "H001" in scores
        assert "H002" in scores
        assert isinstance(scores["H001"], float)

    def test_score_candidates_unknown_hash(self, sample_index):
        scores = sample_index.score_candidates(
            "test",
            candidate_iri_hashes=["UNKNOWN"],
        )
        assert "UNKNOWN" not in scores

    def test_query_before_build_raises(self):
        from app.services.embedding.folio_index import FOLIOEmbeddingIndex

        provider = FakeEmbeddingProvider(dim=8)
        index = FOLIOEmbeddingIndex(
            provider=provider,
            iri_hashes=["H001"],
            labels=["Test"],
            definitions=[None],
            branches=["Test"],
        )
        with pytest.raises(RuntimeError, match="not built"):
            index.query("test")


class TestDiskCache:
    def test_save_and_load_cache(self, tmp_path):
        from app.services.embedding.folio_index import FOLIOEmbeddingIndex

        provider = FakeEmbeddingProvider(dim=8)

        # Build index
        index1 = FOLIOEmbeddingIndex(
            provider=provider,
            iri_hashes=["H001", "H002"],
            labels=["Alpha", "Beta"],
            definitions=["Def A", None],
            branches=["B1", "B2"],
        )
        # Manually save
        index1.build()
        cache_path = tmp_path / "test_cache.pkl"
        index1._save_cache(cache_path)

        # Load into new index
        index2 = FOLIOEmbeddingIndex(
            provider=provider,
            iri_hashes=["H001", "H002"],
            labels=["Alpha", "Beta"],
            definitions=["Def A", None],
            branches=["B1", "B2"],
        )
        index2._load_cache(cache_path)
        assert index2._index is not None
        assert index2._index.ntotal == 2

        # Query should work
        results = index2.query("alpha", top_k=2)
        assert len(results) == 2


class TestBaseEmbeddingProvider:
    def test_normalize(self):
        vec = np.array([[3.0, 4.0]], dtype=np.float32)
        normed = BaseEmbeddingProvider._normalize(vec)
        assert abs(np.linalg.norm(normed) - 1.0) < 1e-5

    def test_normalize_zero_vector(self):
        vec = np.array([[0.0, 0.0]], dtype=np.float32)
        normed = BaseEmbeddingProvider._normalize(vec)
        # Should not produce NaN
        assert not np.any(np.isnan(normed))


class TestEmbeddingModels:
    def test_provider_type_enum(self):
        from app.models.embedding_models import EmbeddingProviderType
        assert EmbeddingProviderType.local == "local"
        assert EmbeddingProviderType.ollama == "ollama"
        assert EmbeddingProviderType.openai == "openai"

    def test_embedding_config(self):
        from app.models.embedding_models import EmbeddingConfig
        config = EmbeddingConfig()
        assert config.provider == "local"
        assert config.disabled is False

    def test_embedding_status(self):
        from app.models.embedding_models import EmbeddingStatus
        status = EmbeddingStatus(provider="local", model="test")
        assert status.index_size == 0
