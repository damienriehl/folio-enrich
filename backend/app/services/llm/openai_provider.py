from __future__ import annotations

# Backward-compatibility redirect — use OpenAICompatProvider
from app.services.llm.openai_compat import OpenAICompatProvider as OpenAIProvider

__all__ = ["OpenAIProvider"]
