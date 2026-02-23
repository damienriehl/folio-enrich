"""Dynamic model pricing via LiteLLM's public pricing database."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

# ~800 input tokens + ~200 output tokens per pipeline node (estimate)
INPUT_TOKENS_PER_NODE = 800
OUTPUT_TOKENS_PER_NODE = 200

CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

_cache: dict[str, float] = {}
_cache_fetched_at: float = 0.0


def _is_cache_valid() -> bool:
    return bool(_cache) and (time.time() - _cache_fetched_at) < CACHE_TTL_SECONDS


async def fetch_pricing() -> tuple[dict[str, float], float]:
    """Return (prices, fetched_at) -- prices maps model_id to cost_per_node."""
    global _cache, _cache_fetched_at

    if _is_cache_valid():
        return _cache, _cache_fetched_at

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(LITELLM_PRICING_URL)
            resp.raise_for_status()
            raw = resp.json()
    except Exception:
        logger.warning("Failed to fetch LiteLLM pricing data", exc_info=True)
        return _cache, _cache_fetched_at  # stale cache or empty

    prices: dict[str, float] = {}
    for model_id, info in raw.items():
        if not isinstance(info, dict):
            continue
        input_cost = info.get("input_cost_per_token")
        output_cost = info.get("output_cost_per_token")
        if input_cost is None or output_cost is None:
            continue
        try:
            cost_per_node = (
                float(input_cost) * INPUT_TOKENS_PER_NODE
                + float(output_cost) * OUTPUT_TOKENS_PER_NODE
            )
        except (ValueError, TypeError):
            continue
        prices[model_id] = cost_per_node

        # Also store without provider prefix (e.g. "openai/gpt-4o" -> "gpt-4o")
        if "/" in model_id:
            short = model_id.split("/", 1)[1]
            if short not in prices:
                prices[short] = cost_per_node

    _cache = prices
    _cache_fetched_at = time.time()
    logger.info("Loaded pricing for %d models", len(prices))
    return prices, _cache_fetched_at
