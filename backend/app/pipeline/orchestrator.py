from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.pipeline.stages.ingestion_stage import IngestionStage
from app.pipeline.stages.normalization_stage import NormalizationStage
from app.pipeline.stages.entity_ruler_stage import EntityRulerStage
from app.pipeline.stages.llm_concept_stage import LLMConceptStage
from app.pipeline.stages.reconciliation_stage import ReconciliationStage
from app.pipeline.stages.resolution_stage import ResolutionStage
from app.pipeline.stages.string_match_stage import StringMatchStage
from app.pipeline.stages.branch_judge_stage import BranchJudgeStage
from app.pipeline.stages.metadata_stage import MetadataStage
from app.pipeline.stages.dependency_stage import DependencyStage
from app.services.llm.base import LLMProvider
from app.storage.job_store import JobStore

logger = logging.getLogger(__name__)


def _get_embedding_service():
    """Get the singleton EmbeddingService if it has indexed labels."""
    try:
        from app.services.embedding.service import EmbeddingService
        svc = EmbeddingService.get_instance()
        return svc if svc.index_size > 0 else None
    except Exception:
        return None


def build_stages(llm: LLMProvider | None = None) -> list[PipelineStage]:
    """Build the full pipeline stage list. LLM-dependent stages are included
    only when an LLM provider is available; otherwise they are skipped gracefully."""
    embedding_service = _get_embedding_service()

    stages: list[PipelineStage] = [
        IngestionStage(),
        NormalizationStage(),
        EntityRulerStage(embedding_service=embedding_service),
    ]

    if llm is not None:
        stages.append(LLMConceptStage(llm))

    stages.append(ReconciliationStage(embedding_service=embedding_service))
    stages.append(ResolutionStage())

    if llm is not None:
        stages.append(BranchJudgeStage(llm))

    stages.append(StringMatchStage())

    if llm is not None:
        stages.append(MetadataStage(llm))

    stages.append(DependencyStage())

    return stages


def _try_get_llm() -> LLMProvider | None:
    """Try to create an LLM provider from settings. Returns None if no API key."""
    try:
        from app.config import settings
        from app.models.llm_models import LLMProviderType
        from app.services.llm.registry import REQUIRES_API_KEY, get_provider
        from app.api.routes.settings import _get_api_key_for_provider

        provider_name = settings.llm_provider.replace("-", "_")
        if provider_name == "lm_studio":
            provider_name = "lmstudio"

        try:
            provider_type = LLMProviderType(provider_name)
        except ValueError:
            logger.warning("Unknown LLM provider %s — LLM stages will be skipped", provider_name)
            return None

        api_key = _get_api_key_for_provider(provider_type)

        if REQUIRES_API_KEY.get(provider_type, True) and not api_key:
            logger.warning(
                "No API key for %s — LLM stages will be skipped",
                provider_type.value,
            )
            return None

        return get_provider(
            provider_type=provider_type,
            api_key=api_key,
            model=settings.llm_model,
        )
    except Exception:
        logger.warning("Failed to create LLM provider — LLM stages will be skipped", exc_info=True)
        return None


class PipelineOrchestrator:
    def __init__(
        self,
        job_store: JobStore,
        stages: list[PipelineStage] | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self.job_store = job_store
        if stages is not None:
            self.stages = stages
        else:
            self.stages = build_stages(llm)

    async def run(self, job: Job) -> Job:
        try:
            for stage in self.stages:
                logger.info("Running stage %s for job %s", stage.name, job.id)
                try:
                    job = await stage.execute(job)
                except Exception as stage_err:
                    logger.warning(
                        "Stage %s failed for job %s: %s — continuing",
                        stage.name, job.id, stage_err,
                    )
                    # Non-fatal: continue pipeline with partial results
                    continue
                job.updated_at = datetime.now(timezone.utc)
                await self.job_store.save(job)

            job.status = JobStatus.COMPLETED
            job.updated_at = datetime.now(timezone.utc)
            await self.job_store.save(job)

        except Exception as e:
            logger.exception("Pipeline failed for job %s", job.id)
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.updated_at = datetime.now(timezone.utc)
            await self.job_store.save(job)

        return job
