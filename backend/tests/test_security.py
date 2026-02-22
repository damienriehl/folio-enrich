import pytest

from app.services.cache import LRUTTLCache


class TestLRUTTLCache:
    def test_set_and_get(self):
        cache = LRUTTLCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent(self):
        cache = LRUTTLCache()
        assert cache.get("missing") is None

    def test_lru_eviction(self):
        cache = LRUTTLCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # Should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_ttl_expiry(self):
        cache = LRUTTLCache(ttl_seconds=0)  # Immediate expiry
        cache.set("key", "value")
        import time
        time.sleep(0.01)
        assert cache.get("key") is None

    def test_clear(self):
        cache = LRUTTLCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0

    def test_size(self):
        cache = LRUTTLCache()
        assert cache.size == 0
        cache.set("a", 1)
        assert cache.size == 1


class TestSecurityMiddleware:
    @pytest.mark.asyncio
    async def test_health_passes_security(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_normal_post_passes(self, client):
        resp = await client.post(
            "/enrich",
            json={"content": "Test.", "format": "plain_text"},
        )
        assert resp.status_code == 202


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_404_for_missing_job(self, client):
        from uuid import uuid4
        resp = await client.get(f"/enrich/{uuid4()}")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data
