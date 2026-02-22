from __future__ import annotations

from app.services.llm.openai_provider import OpenAIProvider


class LMStudioProvider(OpenAIProvider):
    """LM Studio provider — uses OpenAI-compatible API at localhost:1234."""

    def __init__(
        self,
        model: str = "local-model",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key or "lm-studio",  # LM Studio doesn't need a real key
            base_url=base_url or "http://localhost:1234/v1",
        )
