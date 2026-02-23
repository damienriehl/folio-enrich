"""Tests for the dynamic LLM provider system."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.llm_models import LLMProviderType, ModelInfo
from app.services.llm.base import LLMProvider
from app.services.llm.registry import (
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    KNOWN_MODELS,
    PROVIDER_DISPLAY_NAMES,
    REQUIRES_API_KEY,
    get_provider,
)
from app.services.llm.url_validator import validate_base_url


# ── Enum tests ──────────────────────────────────────────────────

class TestLLMProviderType:
    def test_has_all_13_values(self):
        assert len(LLMProviderType) == 13

    def test_expected_providers(self):
        expected = {
            "openai", "anthropic", "google", "mistral", "cohere",
            "meta_llama", "ollama", "lmstudio", "custom", "groq",
            "xai", "github_models", "llamafile",
        }
        actual = {p.value for p in LLMProviderType}
        assert actual == expected

    def test_string_enum(self):
        assert LLMProviderType.openai == "openai"
        assert isinstance(LLMProviderType.openai, str)


# ── Registry metadata tests ────────────────────────────────────

class TestRegistryMetadata:
    def test_all_providers_have_default_urls(self):
        for pt in LLMProviderType:
            assert pt in DEFAULT_BASE_URLS, f"Missing default URL for {pt}"

    def test_all_providers_have_default_models(self):
        for pt in LLMProviderType:
            assert pt in DEFAULT_MODELS, f"Missing default model for {pt}"

    def test_all_providers_have_display_names(self):
        for pt in LLMProviderType:
            assert pt in PROVIDER_DISPLAY_NAMES, f"Missing display name for {pt}"

    def test_all_providers_have_requires_api_key(self):
        for pt in LLMProviderType:
            assert pt in REQUIRES_API_KEY, f"Missing requires_api_key for {pt}"

    def test_known_models_for_cloud_providers(self):
        cloud = [pt for pt in LLMProviderType if REQUIRES_API_KEY.get(pt, True)]
        for pt in cloud:
            models = KNOWN_MODELS.get(pt, [])
            assert len(models) > 0, f"No known models for cloud provider {pt}"

    def test_local_providers_dont_require_keys(self):
        for name in ("ollama", "lmstudio", "custom", "llamafile"):
            pt = LLMProviderType(name)
            assert REQUIRES_API_KEY[pt] is False


# ── get_provider factory tests ──────────────────────────────────

class TestGetProvider:
    def test_openai_returns_openai_compat(self):
        from app.services.llm.openai_compat import OpenAICompatProvider
        p = get_provider("openai", api_key="test-key")
        assert isinstance(p, OpenAICompatProvider)

    def test_anthropic_returns_anthropic_provider(self):
        from app.services.llm.anthropic_provider import AnthropicProvider
        p = get_provider("anthropic", api_key="test-key")
        assert isinstance(p, AnthropicProvider)

    def test_google_returns_google_provider(self):
        from app.services.llm.google_provider import GoogleProvider
        p = get_provider("google", api_key="test-key")
        assert isinstance(p, GoogleProvider)

    def test_cohere_returns_cohere_provider(self):
        from app.services.llm.cohere_provider import CohereProvider
        p = get_provider("cohere", api_key="test-key")
        assert isinstance(p, CohereProvider)

    def test_github_models_returns_github_provider(self):
        from app.services.llm.github_models_provider import GitHubModelsProvider
        p = get_provider("github_models", api_key="test-key")
        assert isinstance(p, GitHubModelsProvider)

    def test_ollama_returns_openai_compat(self):
        from app.services.llm.openai_compat import OpenAICompatProvider
        p = get_provider("ollama")
        assert isinstance(p, OpenAICompatProvider)
        assert p.base_url == "http://localhost:11434/v1"

    def test_lmstudio_returns_openai_compat(self):
        from app.services.llm.openai_compat import OpenAICompatProvider
        p = get_provider("lmstudio")
        assert isinstance(p, OpenAICompatProvider)
        assert p.base_url == "http://localhost:1234/v1"

    def test_groq_returns_openai_compat(self):
        from app.services.llm.openai_compat import OpenAICompatProvider
        p = get_provider("groq", api_key="test-key")
        assert isinstance(p, OpenAICompatProvider)

    def test_enum_input(self):
        p = get_provider(LLMProviderType.openai, api_key="test-key")
        assert p is not None

    def test_backward_compat_lm_studio(self):
        """Old name 'lm_studio' should map to 'lmstudio'."""
        p = get_provider("lm_studio")
        assert p is not None

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_provider("nonexistent_provider_xyz")

    def test_local_providers_get_placeholder_key(self):
        p = get_provider("ollama")
        assert p.api_key == "ollama"

    def test_custom_base_url(self):
        p = get_provider("openai", api_key="k", base_url="https://custom.api.com/v1")
        assert p.base_url == "https://custom.api.com/v1"

    def test_custom_model(self):
        p = get_provider("openai", api_key="k", model="gpt-4")
        assert p.model == "gpt-4"


# ── SSRF validator tests ────────────────────────────────────────

class TestSSRFValidator:
    def test_cloud_requires_https(self):
        with pytest.raises(ValueError, match="requires HTTPS"):
            validate_base_url("http://api.openai.com/v1", LLMProviderType.openai)

    def test_cloud_allows_https(self):
        # May raise DNS error but not HTTPS error
        try:
            validate_base_url("https://api.openai.com/v1", LLMProviderType.openai)
        except ValueError as e:
            assert "requires HTTPS" not in str(e)

    def test_local_allows_http(self):
        # Local providers allow HTTP — may raise DNS but not scheme error
        try:
            validate_base_url("http://localhost:11434/v1", LLMProviderType.ollama)
        except ValueError as e:
            assert "requires HTTPS" not in str(e)

    def test_missing_scheme_raises(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_base_url("api.openai.com/v1", LLMProviderType.openai)

    def test_missing_hostname_raises(self):
        with pytest.raises(ValueError):
            validate_base_url("https://", LLMProviderType.openai)


# ── OpenAICompatProvider tests ──────────────────────────────────

class TestOpenAICompatProvider:
    @pytest.mark.asyncio
    async def test_list_models_with_mock(self):
        from app.services.llm.openai_compat import OpenAICompatProvider

        provider = OpenAICompatProvider(api_key="test", base_url="https://api.openai.com/v1")

        mock_model_1 = MagicMock()
        mock_model_1.id = "gpt-4o"
        mock_model_2 = MagicMock()
        mock_model_2.id = "gpt-4o-mini"

        mock_response = MagicMock()
        mock_response.__iter__ = MagicMock(return_value=iter([mock_model_1, mock_model_2]))

        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        models = await provider.list_models()
        assert len(models) == 2
        assert all(isinstance(m, ModelInfo) for m in models)
        # Sorted by ID
        assert models[0].id == "gpt-4o"
        assert models[1].id == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_test_connection_with_model(self):
        from app.services.llm.openai_compat import OpenAICompatProvider

        provider = OpenAICompatProvider(
            api_key="test", base_url="https://api.openai.com/v1", model="gpt-4o-mini"
        )

        mock_choice = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.test_connection()
        assert result is True


# ── AnthropicProvider tests ─────────────────────────────────────

class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_list_models_with_fallback(self):
        from app.services.llm.anthropic_provider import AnthropicProvider, _FALLBACK_MODELS

        provider = AnthropicProvider(api_key="test")

        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(side_effect=Exception("API error"))
        provider._client = mock_client

        models = await provider.list_models()
        assert len(models) == len(_FALLBACK_MODELS)
        assert models[0].id == _FALLBACK_MODELS[0].id

    @pytest.mark.asyncio
    async def test_list_models_dynamic(self):
        from app.services.llm.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(api_key="test")

        mock_model = MagicMock()
        mock_model.id = "claude-sonnet-4-20250514"
        mock_model.display_name = "Claude Sonnet 4"

        mock_response = MagicMock()
        mock_response.data = [mock_model]

        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        models = await provider.list_models()
        assert len(models) == 1
        assert models[0].id == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_test_connection(self):
        from app.services.llm.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(api_key="test", model="claude-sonnet-4-20250514")

        mock_content = MagicMock()
        mock_content.text = "Hi"
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.test_connection()
        assert result is True


# ── GoogleProvider tests ────────────────────────────────────────

class TestGoogleProvider:
    @pytest.mark.asyncio
    async def test_list_models_with_mock(self):
        from app.services.llm.google_provider import GoogleProvider

        provider = GoogleProvider(api_key="test")

        mock_data = {
            "models": [
                {
                    "name": "models/gemini-2.0-flash",
                    "displayName": "Gemini 2.0 Flash",
                    "supportedGenerationMethods": ["generateContent"],
                    "inputTokenLimit": 1048576,
                },
                {
                    "name": "models/embedding-001",
                    "displayName": "Embedding",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        }

        with patch("app.services.llm.google_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_data
            mock_resp.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            models = await provider.list_models()
            # Should only include generateContent models
            assert len(models) == 1
            assert models[0].id == "gemini-2.0-flash"
            assert models[0].context_window == 1048576


# ── CohereProvider tests ────────────────────────────────────────

class TestCohereProvider:
    @pytest.mark.asyncio
    async def test_list_models_with_mock(self):
        from app.services.llm.cohere_provider import CohereProvider

        provider = CohereProvider(api_key="test")

        mock_data = {
            "models": [
                {"name": "command-r-plus", "context_length": 128000},
                {"name": "command-r", "context_length": 128000},
            ]
        }

        with patch("app.services.llm.cohere_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_data
            mock_resp.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            models = await provider.list_models()
            assert len(models) == 2
            assert models[0].id == "command-r"
            assert models[1].id == "command-r-plus"
