from __future__ import annotations

from app.services.llm.base import LLMProvider

_PROVIDERS: dict[str, type[LLMProvider]] = {}


def register_provider(name: str, cls: type[LLMProvider]) -> None:
    _PROVIDERS[name] = cls


def get_provider(name: str, **kwargs) -> LLMProvider:
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown LLM provider: {name}. Available: {list(_PROVIDERS.keys())}"
        )
    return cls(**kwargs)


def _register_defaults() -> None:
    from app.services.llm.anthropic_provider import AnthropicProvider
    from app.services.llm.openai_provider import OpenAIProvider

    register_provider("openai", OpenAIProvider)
    register_provider("anthropic", AnthropicProvider)


_register_defaults()
