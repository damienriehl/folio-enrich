from __future__ import annotations

from app.services.llm.openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    """Ollama provider — uses OpenAI-compatible API at localhost:11434."""

    def __init__(
        self,
        model: str = "llama3.2",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key or "ollama",  # Ollama doesn't need a real key
            base_url=base_url or "http://localhost:11434/v1",
        )
