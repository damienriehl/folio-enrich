from __future__ import annotations

from app.models.llm_models import LLMProviderType, ModelInfo
from app.services.llm.base import LLMProvider

DEFAULT_BASE_URLS: dict[LLMProviderType, str] = {
    LLMProviderType.openai: "https://api.openai.com/v1",
    LLMProviderType.anthropic: "https://api.anthropic.com",
    LLMProviderType.google: "https://generativelanguage.googleapis.com/v1beta",
    LLMProviderType.mistral: "https://api.mistral.ai/v1",
    LLMProviderType.cohere: "https://api.cohere.com/v2",
    LLMProviderType.meta_llama: "https://api.llama.com/v1",
    LLMProviderType.ollama: "http://localhost:11434/v1",
    LLMProviderType.lmstudio: "http://localhost:1234/v1",
    LLMProviderType.custom: "http://localhost:8080/v1",
    LLMProviderType.groq: "https://api.groq.com/openai/v1",
    LLMProviderType.xai: "https://api.x.ai/v1",
    LLMProviderType.github_models: "https://models.github.ai/inference",
    LLMProviderType.llamafile: "http://localhost:8080/v1",
}

DEFAULT_MODELS: dict[LLMProviderType, str] = {
    LLMProviderType.openai: "gpt-4o",                  # mid: between mini and o3
    LLMProviderType.anthropic: "claude-sonnet-4-6",     # mid: between Haiku and Opus
    LLMProviderType.google: "gemini-2.5-flash",         # mid: between flash-lite and pro
    LLMProviderType.mistral: "mistral-medium-latest",   # mid: between small and large
    LLMProviderType.cohere: "command-a-03-2025",        # mid: current-gen flagship
    LLMProviderType.meta_llama: "llama-4-scout",        # mid: lighter Llama 4
    LLMProviderType.ollama: "",
    LLMProviderType.lmstudio: "",
    LLMProviderType.custom: "",
    LLMProviderType.groq: "llama-3.3-70b-versatile",   # mid: between 8B and 120B
    LLMProviderType.xai: "grok-3",                     # mid: between mini and grok 4
    LLMProviderType.github_models: "openai/gpt-4o",    # mid
    LLMProviderType.llamafile: "",
}

PROVIDER_DISPLAY_NAMES: dict[LLMProviderType, str] = {
    LLMProviderType.openai: "OpenAI",
    LLMProviderType.anthropic: "Anthropic",
    LLMProviderType.google: "Google Gemini",
    LLMProviderType.mistral: "Mistral AI",
    LLMProviderType.cohere: "Cohere",
    LLMProviderType.meta_llama: "Meta Llama",
    LLMProviderType.ollama: "Ollama (Local)",
    LLMProviderType.lmstudio: "LM Studio (Local)",
    LLMProviderType.custom: "Custom OpenAI-Compatible",
    LLMProviderType.groq: "Groq",
    LLMProviderType.xai: "xAI (Grok)",
    LLMProviderType.github_models: "GitHub Models",
    LLMProviderType.llamafile: "Llamafile (Local)",
}

REQUIRES_API_KEY: dict[LLMProviderType, bool] = {
    LLMProviderType.openai: True,
    LLMProviderType.anthropic: True,
    LLMProviderType.google: True,
    LLMProviderType.mistral: True,
    LLMProviderType.cohere: True,
    LLMProviderType.meta_llama: True,
    LLMProviderType.ollama: False,
    LLMProviderType.lmstudio: False,
    LLMProviderType.custom: False,
    LLMProviderType.groq: True,
    LLMProviderType.xai: True,
    LLMProviderType.github_models: True,
    LLMProviderType.llamafile: False,
}

# Well-known models per provider (shown without API key; refresh fetches live).
# Ordered: oldest/cheapest → newest/most powerful.
KNOWN_MODELS: dict[LLMProviderType, list[ModelInfo]] = {
    LLMProviderType.openai: [
        ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", context_window=128000),
        ModelInfo(id="gpt-4.1-nano", name="GPT-4.1 Nano", context_window=1047576),
        ModelInfo(id="o3-mini", name="o3 Mini", context_window=200000),
        ModelInfo(id="gpt-4o", name="GPT-4o", context_window=128000),
        ModelInfo(id="gpt-4.1-mini", name="GPT-4.1 Mini", context_window=1047576),
        ModelInfo(id="o4-mini", name="o4 Mini", context_window=200000),
        ModelInfo(id="gpt-4.1", name="GPT-4.1", context_window=1047576),
        ModelInfo(id="o3", name="o3", context_window=200000),
    ],
    LLMProviderType.anthropic: [
        ModelInfo(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5", context_window=200000),
        ModelInfo(id="claude-sonnet-4-5-20250929", name="Claude Sonnet 4.5", context_window=200000),
        ModelInfo(id="claude-sonnet-4-6", name="Claude Sonnet 4.6", context_window=200000),
        ModelInfo(id="claude-opus-4-6", name="Claude Opus 4.6", context_window=200000),
    ],
    LLMProviderType.google: [
        ModelInfo(id="gemini-2.5-flash-lite", name="Gemini 2.5 Flash-Lite", context_window=1048576),
        ModelInfo(id="gemini-2.5-flash", name="Gemini 2.5 Flash", context_window=1048576),
        ModelInfo(id="gemini-3-flash-preview", name="Gemini 3 Flash", context_window=200000),
        ModelInfo(id="gemini-2.5-pro", name="Gemini 2.5 Pro", context_window=1048576),
        ModelInfo(id="gemini-3-pro-preview", name="Gemini 3 Pro", context_window=1048576),
        ModelInfo(id="gemini-3.1-pro-preview", name="Gemini 3.1 Pro", context_window=1048576),
    ],
    LLMProviderType.mistral: [
        ModelInfo(id="mistral-small-latest", name="Mistral Small 3.2", context_window=128000),
        ModelInfo(id="codestral-latest", name="Codestral", context_window=128000),
        ModelInfo(id="mistral-medium-latest", name="Mistral Medium 3.1", context_window=128000),
        ModelInfo(id="devstral-latest", name="Devstral 2", context_window=256000),
        ModelInfo(id="mistral-large-latest", name="Mistral Large 3", context_window=260000),
    ],
    LLMProviderType.cohere: [
        ModelInfo(id="command-r-08-2024", name="Command R", context_window=128000),
        ModelInfo(id="command-r-plus-08-2024", name="Command R+", context_window=128000),
        ModelInfo(id="command-a-03-2025", name="Command A", context_window=256000),
        ModelInfo(id="command-a-vision-07-2025", name="Command A Vision", context_window=128000),
        ModelInfo(id="command-a-reasoning-08-2025", name="Command A Reasoning", context_window=256000),
    ],
    LLMProviderType.meta_llama: [
        ModelInfo(id="llama-3.3-70b-instruct", name="Llama 3.3 70B", context_window=128000),
        ModelInfo(id="llama-4-scout", name="Llama 4 Scout", context_window=512000),
        ModelInfo(id="llama-4-maverick", name="Llama 4 Maverick", context_window=256000),
    ],
    LLMProviderType.groq: [
        ModelInfo(id="llama-3.1-8b-instant", name="Llama 3.1 8B Instant", context_window=128000),
        ModelInfo(id="llama-3.3-70b-versatile", name="Llama 3.3 70B Versatile", context_window=128000),
        ModelInfo(id="qwen/qwen3-32b", name="Qwen3 32B", context_window=131072),
        ModelInfo(id="meta-llama/llama-4-scout-17b-16e-instruct", name="Llama 4 Scout", context_window=131072),
        ModelInfo(id="openai/gpt-oss-120b", name="GPT-OSS 120B", context_window=131072),
    ],
    LLMProviderType.xai: [
        ModelInfo(id="grok-3-mini", name="Grok 3 Mini", context_window=131072),
        ModelInfo(id="grok-3", name="Grok 3", context_window=131072),
        ModelInfo(id="grok-4-0709", name="Grok 4", context_window=256000),
    ],
    LLMProviderType.github_models: [
        ModelInfo(id="openai/gpt-4o-mini", name="OpenAI GPT-4o Mini", context_window=128000),
        ModelInfo(id="meta/llama-3.3-70b-instruct", name="Meta Llama 3.3 70B", context_window=128000),
        ModelInfo(id="openai/gpt-4o", name="OpenAI GPT-4o", context_window=128000),
        ModelInfo(id="mistral-ai/mistral-large-2411", name="Mistral Large", context_window=128000),
    ],
    # Local providers: no known models (user-dependent)
    LLMProviderType.ollama: [],
    LLMProviderType.lmstudio: [],
    LLMProviderType.custom: [],
    LLMProviderType.llamafile: [],
}

# Provider type → concrete class mapping (lazy imports)
_OPENAI_COMPAT_PROVIDERS: set[LLMProviderType] = {
    LLMProviderType.openai,
    LLMProviderType.mistral,
    LLMProviderType.meta_llama,
    LLMProviderType.ollama,
    LLMProviderType.lmstudio,
    LLMProviderType.custom,
    LLMProviderType.groq,
    LLMProviderType.xai,
    LLMProviderType.llamafile,
}


def get_provider(
    provider_type: LLMProviderType | str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    **kwargs,
) -> LLMProvider:
    """Factory: create an LLM provider instance.

    Accepts both LLMProviderType enum and string names for backward compatibility.
    """
    # Normalize string to enum
    if isinstance(provider_type, str):
        # Support old names: "lm_studio" → "lmstudio"
        name = provider_type.replace("-", "_")
        if name == "lm_studio":
            name = "lmstudio"
        try:
            provider_type = LLMProviderType(name)
        except ValueError:
            available = [p.value for p in LLMProviderType]
            raise ValueError(
                f"Unknown LLM provider: {provider_type}. Available: {available}"
            )

    # Resolve defaults
    resolved_base_url = base_url or DEFAULT_BASE_URLS.get(provider_type)
    resolved_model = model or DEFAULT_MODELS.get(provider_type)

    # For local providers that don't need a real key, supply a placeholder
    if not REQUIRES_API_KEY.get(provider_type, True) and not api_key:
        api_key = provider_type.value

    if provider_type == LLMProviderType.anthropic:
        from app.services.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=api_key,
            base_url=resolved_base_url,
            model=resolved_model,
        )

    if provider_type == LLMProviderType.google:
        from app.services.llm.google_provider import GoogleProvider

        return GoogleProvider(
            api_key=api_key,
            base_url=resolved_base_url,
            model=resolved_model,
        )

    if provider_type == LLMProviderType.cohere:
        from app.services.llm.cohere_provider import CohereProvider

        return CohereProvider(
            api_key=api_key,
            base_url=resolved_base_url,
            model=resolved_model,
        )

    if provider_type == LLMProviderType.github_models:
        from app.services.llm.github_models_provider import GitHubModelsProvider

        return GitHubModelsProvider(
            api_key=api_key,
            base_url=resolved_base_url,
            model=resolved_model,
        )

    if provider_type in _OPENAI_COMPAT_PROVIDERS:
        from app.services.llm.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(
            api_key=api_key,
            base_url=resolved_base_url,
            model=resolved_model,
        )

    raise ValueError(f"No provider implementation for: {provider_type.value}")
