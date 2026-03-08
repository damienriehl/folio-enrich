from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FOLIO Enrich"
    debug: bool = False

    # Job storage
    jobs_dir: Path = Path(os.path.expanduser("~/.folio-enrich/jobs"))

    # Feedback storage
    feedback_dir: Path = Path(os.path.expanduser("~/.folio-enrich/feedback"))

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]

    # Chunking
    max_chunk_chars: int = 3000
    chunk_overlap_chars: int = 200

    # LLM — global defaults (used when per-task overrides are not set)
    llm_provider: str = "ollama"
    llm_model: str = ""  # empty = adaptive tier selection for Ollama
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    mistral_api_key: str = ""
    cohere_api_key: str = ""
    meta_llama_api_key: str = ""
    groq_api_key: str = ""
    xai_api_key: str = ""
    github_models_api_key: str = ""

    # Per-task LLM overrides (empty = use global llm_provider/llm_model)
    llm_classifier_provider: str = ""
    llm_classifier_model: str = ""
    llm_extractor_provider: str = ""
    llm_extractor_model: str = ""
    llm_concept_provider: str = ""
    llm_concept_model: str = ""
    llm_branch_judge_provider: str = ""
    llm_branch_judge_model: str = ""
    llm_area_of_law_provider: str = ""
    llm_area_of_law_model: str = ""
    llm_synthetic_provider: str = ""
    llm_synthetic_model: str = ""
    llm_document_type_provider: str = ""
    llm_document_type_model: str = ""

    # Ollama auto-management
    ollama_auto_manage: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model_simple: str = "qwen3:4b"     # ~2.5GB — classification, area_of_law
    ollama_model_medium: str = "qwen3:8b"     # ~5GB — concept, branch_judge, synthetic
    ollama_model_complex: str = "qwen3:14b"   # ~9GB — metadata extraction, individual, property

    # Embedding
    embedding_provider: str = "local"  # local, ollama, openai
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_disabled: bool = False
    semantic_similarity_threshold: float = 0.80

    # Contextual reranking — disabled by default (2026-02-27).
    # The 50/50 LLM-context / pipeline-score blend was degrading precision
    # and recall in testing: the LLM context scores often inflated marginal
    # matches and diluted high-confidence pipeline signals, producing noisier
    # annotations overall.  Re-enable only after validating that blended
    # scores improve F1 on a representative evaluation set.
    contextual_rerank_enabled: bool = False

    # Individual extraction
    individual_extraction_enabled: bool = True
    individual_regex_only: bool = False  # Skip LLM, only library/regex extractors
    llm_individual_provider: str = ""
    llm_individual_model: str = ""

    # Property extraction
    property_extraction_enabled: bool = True
    property_regex_only: bool = False  # Skip LLM, only Aho-Corasick matching
    llm_property_provider: str = ""
    llm_property_model: str = ""

    # FOLIO OWL auto-update
    folio_auto_update: bool = True
    folio_update_check_interval_hours: int = 24

    # Triple extraction & POS tagging
    triple_extraction_enabled: bool = True
    pos_tagging_enabled: bool = True

    # POS confidence modulation
    pos_confidence_enabled: bool = True           # Master switch for all POS adjustments
    pos_concept_mismatch_penalty: float = 0.15    # Penalty when concept span POS != expected
    pos_property_mismatch_penalty: float = 0.12   # Penalty when property span POS mismatches
    pos_branch_affinity_boost: float = 0.05       # Boost/penalty for POS-branch alignment

    # Candidates
    max_candidates: int = 5

    # Job management
    job_retention_days: int = 30
    max_concurrent_jobs: int = 10
    stale_job_timeout_minutes: int = 30

    # Rate limiting
    rate_limit_requests: int = 200
    rate_limit_window: int = 60

    # File size limit (bytes)
    max_upload_size: int = 50 * 1024 * 1024  # 50MB

    model_config = {"env_prefix": "FOLIO_ENRICH_"}


settings = Settings()
