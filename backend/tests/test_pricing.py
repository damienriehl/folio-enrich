"""Tests for LLM pricing service."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import pricing


def _make_mock_client(mock_data):
    """Create a properly configured mock httpx.AsyncClient."""
    mock_response = MagicMock()
    mock_response.json.return_value = mock_data
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestPricing:
    def setup_method(self):
        """Reset cache before each test."""
        pricing._cache = {}
        pricing._cache_fetched_at = 0.0

    @pytest.mark.asyncio
    async def test_fetch_pricing_parses_response(self):
        mock_data = {
            "gpt-4o": {
                "input_cost_per_token": 0.000005,
                "output_cost_per_token": 0.000015,
            },
            "openai/gpt-4o-mini": {
                "input_cost_per_token": 0.00000015,
                "output_cost_per_token": 0.0000006,
            },
            "not-a-model": "bad data",
            "missing-fields": {"input_cost_per_token": 0.001},
        }

        with patch("app.services.llm.pricing.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client(mock_data)
            prices, fetched_at = await pricing.fetch_pricing()

        assert "gpt-4o" in prices
        assert "openai/gpt-4o-mini" in prices
        assert "gpt-4o-mini" in prices  # short name alias
        assert "not-a-model" not in prices
        assert "missing-fields" not in prices
        assert fetched_at > 0

    @pytest.mark.asyncio
    async def test_cost_calculation(self):
        mock_data = {
            "test-model": {
                "input_cost_per_token": 0.00001,
                "output_cost_per_token": 0.00003,
            },
        }

        with patch("app.services.llm.pricing.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client(mock_data)
            prices, _ = await pricing.fetch_pricing()

        expected = 0.00001 * 800 + 0.00003 * 200
        assert abs(prices["test-model"] - expected) < 1e-10

    @pytest.mark.asyncio
    async def test_cache_ttl(self):
        pricing._cache = {"cached-model": 0.001}
        pricing._cache_fetched_at = time.time()  # Fresh cache

        prices, _ = await pricing.fetch_pricing()
        assert "cached-model" in prices  # Returns from cache, no HTTP call

    @pytest.mark.asyncio
    async def test_stale_cache_refetches(self):
        pricing._cache = {"old-model": 0.001}
        pricing._cache_fetched_at = time.time() - (8 * 24 * 3600)  # 8 days old

        mock_data = {
            "new-model": {
                "input_cost_per_token": 0.001,
                "output_cost_per_token": 0.002,
            },
        }

        with patch("app.services.llm.pricing.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_client(mock_data)
            prices, _ = await pricing.fetch_pricing()

        assert "new-model" in prices
        assert "old-model" not in prices  # Cache replaced

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_stale_cache(self):
        pricing._cache = {"stale-model": 0.001}
        pricing._cache_fetched_at = 0.0  # Expired

        with patch("app.services.llm.pricing.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Network error")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            prices, _ = await pricing.fetch_pricing()

        assert "stale-model" in prices  # Returns stale cache on failure
