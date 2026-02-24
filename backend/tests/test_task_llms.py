"""Tests for per-task LLM routing (TaskLLMs)."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.models.llm_models import ModelInfo
from app.services.llm.base import LLMProvider


# ---------------------------------------------------------------------------
# Fake LLM providers for testing
# ---------------------------------------------------------------------------

class FakeLLM(LLMProvider):
    """Minimal LLM provider stub that records its label."""

    def __init__(self, label: str = "default") -> None:
        super().__init__(api_key="fake", base_url=None, model="fake-model")
        self.label = label

    async def complete(self, prompt: str, **kw: Any) -> str:
        return ""

    async def chat(self, messages: list[dict], **kw: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kw: Any) -> dict:
        return {}

    async def test_connection(self) -> bool:
        return True

    async def list_models(self) -> list[ModelInfo]:
        return []

    def __repr__(self) -> str:
        return f"FakeLLM({self.label!r})"


# ---------------------------------------------------------------------------
# TaskLLMs unit tests
# ---------------------------------------------------------------------------

class TestTaskLLMs:
    def test_all_none_by_default(self):
        from app.pipeline.orchestrator import TaskLLMs
        t = TaskLLMs()
        assert t.classifier is None
        assert t.extractor is None
        assert t.concept is None
        assert t.branch_judge is None
        assert t.area_of_law is None
        assert t.synthetic is None
        assert not t.has_any

    def test_has_any(self):
        from app.pipeline.orchestrator import TaskLLMs
        t = TaskLLMs(concept=FakeLLM())
        assert t.has_any

    def test_metadata_llm_prefers_classifier(self):
        from app.pipeline.orchestrator import TaskLLMs
        c = FakeLLM("classifier")
        e = FakeLLM("extractor")
        t = TaskLLMs(classifier=c, extractor=e)
        assert t.metadata_llm is c

    def test_metadata_llm_falls_back_to_extractor(self):
        from app.pipeline.orchestrator import TaskLLMs
        e = FakeLLM("extractor")
        t = TaskLLMs(extractor=e)
        assert t.metadata_llm is e

    def test_from_settings_all_fallback(self):
        """When no per-task settings are set, all tasks use the fallback."""
        from app.config import settings
        from app.pipeline.orchestrator import TaskLLMs
        fallback = FakeLLM("global")
        # Save originals and ensure all per-task settings are empty
        originals = {}
        for task in ("classifier", "extractor", "concept", "branch_judge", "area_of_law", "synthetic"):
            for suffix in ("provider", "model"):
                attr = f"llm_{task}_{suffix}"
                originals[attr] = getattr(settings, attr)
                setattr(settings, attr, "")
        try:
            t = TaskLLMs.from_settings(fallback=fallback)
            assert t.classifier is fallback
            assert t.extractor is fallback
            assert t.concept is fallback
            assert t.branch_judge is fallback
            assert t.area_of_law is fallback
            assert t.synthetic is fallback
        finally:
            for attr, val in originals.items():
                setattr(settings, attr, val)

    def test_from_settings_task_override(self):
        """When a per-task provider is set, _make_llm is called for that task."""
        from app.config import settings
        from app.pipeline.orchestrator import TaskLLMs
        fallback = FakeLLM("global")
        override = FakeLLM("concept-override")

        def mock_make_llm(provider_name: str, model: str):
            if provider_name == "openai" and model == "gpt-4.1-nano":
                return override
            return None

        originals = {}
        for task in ("classifier", "extractor", "concept", "branch_judge", "area_of_law", "synthetic"):
            for suffix in ("provider", "model"):
                attr = f"llm_{task}_{suffix}"
                originals[attr] = getattr(settings, attr)
                setattr(settings, attr, "")
        # Set concept override
        settings.llm_concept_provider = "openai"
        settings.llm_concept_model = "gpt-4.1-nano"

        try:
            with patch("app.pipeline.orchestrator._make_llm", side_effect=mock_make_llm):
                t = TaskLLMs.from_settings(fallback=fallback)
            assert t.concept is override
            assert t.classifier is fallback
            assert t.branch_judge is fallback
        finally:
            for attr, val in originals.items():
                setattr(settings, attr, val)


# ---------------------------------------------------------------------------
# build_pipeline_config / build_stages with TaskLLMs
# ---------------------------------------------------------------------------

class TestBuildWithTaskLLMs:
    def test_build_stages_uses_task_llms(self):
        """Each stage should receive its task-specific LLM."""
        from app.pipeline.orchestrator import TaskLLMs, build_stages

        concept = FakeLLM("concept")
        branch = FakeLLM("branch")
        classifier = FakeLLM("classifier")
        extractor = FakeLLM("extractor")

        task_llms = TaskLLMs(
            classifier=classifier,
            extractor=extractor,
            concept=concept,
            branch_judge=branch,
        )
        stages = build_stages(llm=None, task_llms=task_llms)
        stage_names = [s.name for s in stages]

        assert "llm_concept_identification" in stage_names
        assert "branch_judge" in stage_names
        assert "metadata" in stage_names

        # Verify the concept stage got the right LLM
        concept_stage = next(s for s in stages if s.name == "llm_concept_identification")
        assert concept_stage.identifier.llm is concept

        # Verify the branch judge stage got the right LLM
        bj_stage = next(s for s in stages if s.name == "branch_judge")
        assert bj_stage.judge.llm is branch

        # Verify metadata stage got separate LLMs
        meta_stage = next(s for s in stages if s.name == "metadata")
        assert meta_stage.classifier.llm is classifier
        assert meta_stage.extractor.llm is extractor

    def test_build_stages_no_llm_skips_stages(self):
        """With no LLM, LLM-dependent stages are omitted."""
        from app.pipeline.orchestrator import TaskLLMs, build_stages

        task_llms = TaskLLMs()  # all None
        stages = build_stages(llm=None, task_llms=task_llms)
        stage_names = [s.name for s in stages]

        assert "llm_concept_identification" not in stage_names
        assert "branch_judge" not in stage_names
        assert "metadata" not in stage_names

    def test_build_stages_fallback_to_global(self):
        """When task_llms is None, global llm is used for all stages."""
        from app.pipeline.orchestrator import build_stages

        global_llm = FakeLLM("global")
        stages = build_stages(llm=global_llm, task_llms=None)
        stage_names = [s.name for s in stages]

        assert "llm_concept_identification" in stage_names
        concept_stage = next(s for s in stages if s.name == "llm_concept_identification")
        assert concept_stage.identifier.llm is global_llm


# ---------------------------------------------------------------------------
# MetadataStage with separate LLMs
# ---------------------------------------------------------------------------

class TestMetadataStageSeparateLLMs:
    def test_separate_llms(self):
        from app.pipeline.stages.metadata_stage import MetadataStage
        c = FakeLLM("classifier")
        e = FakeLLM("extractor")
        stage = MetadataStage(c, classifier_llm=c, extractor_llm=e)
        assert stage.classifier.llm is c
        assert stage.extractor.llm is e

    def test_backward_compatible_single_llm(self):
        from app.pipeline.stages.metadata_stage import MetadataStage
        llm = FakeLLM("single")
        stage = MetadataStage(llm)
        assert stage.classifier.llm is llm
        assert stage.extractor.llm is llm


# ---------------------------------------------------------------------------
# Settings config
# ---------------------------------------------------------------------------

class TestConfigPerTaskSettings:
    def test_default_empty(self):
        from app.config import Settings
        s = Settings()
        assert s.llm_classifier_provider == ""
        assert s.llm_classifier_model == ""
        assert s.llm_synthetic_provider == ""
        assert s.llm_synthetic_model == ""

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("FOLIO_ENRICH_LLM_CONCEPT_PROVIDER", "google")
        monkeypatch.setenv("FOLIO_ENRICH_LLM_CONCEPT_MODEL", "gemini-2.5-flash")
        from app.config import Settings
        s = Settings()
        assert s.llm_concept_provider == "google"
        assert s.llm_concept_model == "gemini-2.5-flash"
        # Global unchanged
        assert s.llm_provider == "google"
