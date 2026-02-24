from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class LLMProviderType(str, Enum):
    google = "google"
    openai = "openai"
    anthropic = "anthropic"
    mistral = "mistral"
    cohere = "cohere"
    meta_llama = "meta_llama"
    ollama = "ollama"
    lmstudio = "lmstudio"
    custom = "custom"
    groq = "groq"
    xai = "xai"
    github_models = "github_models"
    llamafile = "llamafile"


class ModelInfo(BaseModel):
    id: str
    name: str
    context_window: int | None = None


class ConnectionTestRequest(BaseModel):
    provider: LLMProviderType
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    model: str | None = None


class ModelListRequest(BaseModel):
    provider: LLMProviderType
    base_url: str | None = None
    api_key: str | None = None
