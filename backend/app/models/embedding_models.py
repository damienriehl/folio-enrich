"""Models for embedding system configuration and status."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class EmbeddingProviderType(str, Enum):
    local = "local"
    ollama = "ollama"
    openai = "openai"


class EmbeddingConfig(BaseModel):
    provider: EmbeddingProviderType = EmbeddingProviderType.local
    model: str = "all-MiniLM-L6-v2"
    api_key: str | None = None
    base_url: str | None = None
    disabled: bool = False


class EmbeddingStatus(BaseModel):
    provider: str
    model: str
    index_size: int = 0
    faiss_available: bool = False
    disabled: bool = False
