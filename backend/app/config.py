from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FOLIO Enrich"
    debug: bool = False

    # Job storage
    jobs_dir: Path = Path(os.path.expanduser("~/.folio-enrich/jobs"))

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]

    # Chunking
    max_chunk_chars: int = 3000
    chunk_overlap_chars: int = 200

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Rate limiting
    rate_limit_requests: int = 60
    rate_limit_window: int = 60

    # File size limit (bytes)
    max_upload_size: int = 50 * 1024 * 1024  # 50MB

    model_config = {"env_prefix": "FOLIO_ENRICH_"}


settings = Settings()
