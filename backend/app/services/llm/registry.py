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
    LLMProviderType.github_models: "https://models.inference.ai.azure.com",
    LLMProviderType.llamafile: "http://localhost:8080/v1",
}

DEFAULT_MODELS: dict[LLMProviderType, str] = {
    LLMProviderType.openai: "gpt-4o-mini",
    LLMProviderType.anthropic: "claude-sonnet-4-20250514",
    LLMProviderType.google: "gemini-2.0-flash",
    LLMProviderType.mistral: "mistral-small-latest",
    LLMProviderType.cohere: "command-r-plus",
    LLMProviderType.meta_llama: "Llama-4-Scout-17B-16E-Instruct",
    LLMProviderType.ollama: "llama3.2",
    LLMProviderType.lmstudio: "local-model",
    LLMProviderType.custom: "custom-model",
    LLMProviderType.groq: "llama-3.3-70b-versatile",
    LLMProviderType.xai: "grok-3-mini",
    LLMProviderType.github_models: "gpt-4o-mini",
    LLMProviderType.llamafile: "local-model",
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

KNOWN_MODELS: dict[LLMProviderType, list[ModelInfo]] = {
    LLMProviderType.openai: [
        ModelInfo(id="gpt-4o", name="GPT-4o", context_window=128000),
        ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", context_window=128000),
        ModelInfo(id="gpt-4-turbo", name="GPT-4 Turbo", context_window=128000),
        ModelInfo(id="gpt-4", name="GPT-4", context_window=8192),
        ModelInfo(id="gpt-3.5-turbo", name="GPT-3.5 Turbo", context_window=16385),
        ModelInfo(id="o1", name="o1", context_window=200000),
        ModelInfo(id="o1-mini", name="o1 Mini", context_window=128000),
        ModelInfo(id="o3-mini", name="o3 Mini", context_window=200000),
    ],
    LLMProviderType.anthropic: [
        ModelInfo(id="claude-opus-4-20250514", name="Claude Opus 4", context_window=200000),
        ModelInfo(id="claude-sonnet-4-20250514", name="Claude Sonnet 4", context_window=200000),
        ModelInfo(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5", context_window=200000),
        ModelInfo(id="claude-sonnet-4-6-20250219", name="Claude Sonnet 4.6", context_window=200000),
        ModelInfo(id="claude-opus-4-6-20250219", name="Claude Opus 4.6", context_window=200000),
    ],
    LLMProviderType.google: [
        ModelInfo(id="gemini-2.0-flash", name="Gemini 2.0 Flash", context_window=1048576),
        ModelInfo(id="gemini-2.0-flash-lite", name="Gemini 2.0 Flash-Lite", context_window=1048576),
        ModelInfo(id="gemini-1.5-pro", name="Gemini 1.5 Pro", context_window=2097152),
        ModelInfo(id="gemini-1.5-flash", name="Gemini 1.5 Flash", context_window=1048576),
    ],
    LLMProviderType.mistral: [
        ModelInfo(id="mistral-large-latest", name="Mistral Large", context_window=128000),
        ModelInfo(id="mistral-small-latest", name="Mistral Small", context_window=32000),
        ModelInfo(id="codestral-latest", name="Codestral", context_window=32000),
        ModelInfo(id="open-mistral-nemo", name="Mistral Nemo", context_window=128000),
    ],
    LLMProviderType.cohere: [
        ModelInfo(id="command-r-plus", name="Command R+", context_window=128000),
        ModelInfo(id="command-r", name="Command R", context_window=128000),
        ModelInfo(id="command-light", name="Command Light", context_window=4096),
    ],
    LLMProviderType.meta_llama: [
        ModelInfo(id="Llama-4-Scout-17B-16E-Instruct", name="Llama 4 Scout", context_window=10000000),
        ModelInfo(id="Llama-4-Maverick-17B-128E-Instruct", name="Llama 4 Maverick", context_window=1000000),
        ModelInfo(id="Llama-3.3-70B-Instruct", name="Llama 3.3 70B", context_window=128000),
    ],
    LLMProviderType.groq: [
        ModelInfo(id="llama-3.3-70b-versatile", name="Llama 3.3 70B", context_window=128000),
        ModelInfo(id="llama-3.1-8b-instant", name="Llama 3.1 8B", context_window=128000),
        ModelInfo(id="mixtral-8x7b-32768", name="Mixtral 8x7B", context_window=32768),
        ModelInfo(id="gemma2-9b-it", name="Gemma 2 9B", context_window=8192),
    ],
    LLMProviderType.xai: [
        ModelInfo(id="grok-3-mini", name="Grok 3 Mini", context_window=131072),
        ModelInfo(id="grok-3", name="Grok 3", context_window=131072),
        ModelInfo(id="grok-2", name="Grok 2", context_window=131072),
    ],
    LLMProviderType.github_models: [
        ModelInfo(id="gpt-4o", name="GPT-4o", context_window=128000),
        ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", context_window=128000),
        ModelInfo(id="Phi-3.5-mini-instruct", name="Phi 3.5 Mini", context_window=128000),
    ],
    LLMProviderType.ollama: [
        ModelInfo(id="llama3.2", name="Llama 3.2"),
        ModelInfo(id="llama3.1", name="Llama 3.1"),
        ModelInfo(id="mistral", name="Mistral"),
        ModelInfo(id="codellama", name="Code Llama"),
        ModelInfo(id="gemma2", name="Gemma 2"),
    ],
    LLMProviderType.lmstudio: [
        ModelInfo(id="local-model", name="Local Model"),
    ],
    LLMProviderType.custom: [],
    LLMProviderType.llamafile: [
        ModelInfo(id="local-model", name="Local Model"),
    ],
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
