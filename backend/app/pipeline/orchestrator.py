from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
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
from app.pipeline.stages.individual_stage import EarlyIndividualStage, LLMIndividualStage
from app.pipeline.stages.property_stage import EarlyPropertyStage, LLMPropertyStage
from app.pipeline.stages.document_type_stage import DocumentTypeStage
from app.pipeline.stages.rerank_stage import ContextualRerankStage
from app.services.llm.base import LLMProvider
from app.storage.job_store import JobStore

logger = logging.getLogger(__name__)

# Task names for per-task LLM configuration
LLM_TASKS = ("classifier", "extractor", "concept", "branch_judge", "area_of_law", "synthetic", "individual", "property", "document_type")

# Map task names to TaskLLMs field names (needed when task name is a Python builtin)
_TASK_FIELD_MAP: dict[str, str] = {"property": "property_llm"}


@dataclass
class TaskLLMs:
    """Resolved LLM providers for each pipeline task.

    Each field is either a task-specific LLM or None (meaning LLM unavailable
    for that task).  The ``from_settings`` classmethod resolves per-task env
    vars first, falling back to *fallback* (the global default LLM).
    """

    classifier: LLMProvider | None = None
    extractor: LLMProvider | None = None
    concept: LLMProvider | None = None
    branch_judge: LLMProvider | None = None
    area_of_law: LLMProvider | None = None
    synthetic: LLMProvider | None = None
    individual: LLMProvider | None = None
    property_llm: LLMProvider | None = None
    document_type: LLMProvider | None = None

    # --- convenience helpers ------------------------------------------------

    @property
    def has_any(self) -> bool:
        """True if at least one pipeline LLM is available."""
        return any([self.classifier, self.extractor, self.concept,
                     self.branch_judge, self.area_of_law])

    @property
    def metadata_llm(self) -> LLMProvider | None:
        """Return the first available metadata LLM (classifier or extractor)."""
        return self.classifier or self.extractor

    # --- factory ------------------------------------------------------------

    @classmethod
    def from_settings(cls, fallback: LLMProvider | None = None) -> TaskLLMs:
        """Build TaskLLMs from per-task env vars, falling back to *fallback*."""
        result = cls()
        for task in LLM_TASKS:
            llm = _try_get_task_llm(task, fallback)
            field = _TASK_FIELD_MAP.get(task, task)
            setattr(result, field, llm)
        return result


def _get_embedding_service():
    """Get the singleton EmbeddingService (always available after startup)."""
    try:
        from app.services.embedding.service import EmbeddingService
        svc = EmbeddingService.get_instance()
        if svc.index_size > 0:
            return svc
        logger.warning("Embedding index is empty — semantic features will be disabled")
        return None
    except Exception:
        logger.warning("Failed to get embedding service", exc_info=True)
        return None


@dataclass
class PipelineConfig:
    """Configuration for the three-phase parallel pipeline."""
    pre_parallel: list[PipelineStage] = field(default_factory=list)
    entity_ruler: PipelineStage | None = None
    llm_concept: PipelineStage | None = None
    early_individual: PipelineStage | None = None
    early_property: PipelineStage | None = None
    document_type: PipelineStage | None = None
    post_parallel: list[PipelineStage] = field(default_factory=list)


def build_pipeline_config(
    llm: LLMProvider | None = None,
    task_llms: TaskLLMs | None = None,
) -> PipelineConfig:
    """Build a PipelineConfig with parallel EntityRuler and LLM stages.

    When *task_llms* is provided, each stage uses its task-specific LLM.
    Otherwise the single *llm* is used for all stages (backward-compatible).
    """
    embedding_service = _get_embedding_service()

    concept_llm = (task_llms.concept if task_llms else llm) or llm
    branch_judge_llm = (task_llms.branch_judge if task_llms else llm) or llm
    classifier_llm = (task_llms.classifier if task_llms else llm) or llm
    extractor_llm = (task_llms.extractor if task_llms else llm) or llm
    individual_llm = (task_llms.individual if task_llms else llm) or llm
    property_llm = (task_llms.property_llm if task_llms else llm) or llm
    document_type_llm = (task_llms.document_type if task_llms else llm) or llm

    config = PipelineConfig(
        pre_parallel=[
            IngestionStage(),
            NormalizationStage(),
        ],
        entity_ruler=EntityRulerStage(embedding_service=embedding_service),
    )

    if concept_llm is not None:
        config.llm_concept = LLMConceptStage(concept_llm)

    # Early individual extraction (citations + regex/spaCy) runs in parallel
    config.early_individual = EarlyIndividualStage()

    # Early property extraction (Aho-Corasick) runs in parallel
    config.early_property = EarlyPropertyStage()

    # Early document type classification runs in parallel
    if document_type_llm is not None:
        config.document_type = DocumentTypeStage(document_type_llm)

    config.post_parallel = [
        ReconciliationStage(embedding_service=embedding_service),
        ResolutionStage(embedding_service=embedding_service),
    ]

    if concept_llm is not None:
        config.post_parallel.append(ContextualRerankStage(concept_llm))

    if branch_judge_llm is not None:
        config.post_parallel.append(BranchJudgeStage(branch_judge_llm))

    config.post_parallel.append(StringMatchStage())

    # LLM individual linking (after StringMatch, needs resolved classes)
    config.post_parallel.append(LLMIndividualStage(llm=individual_llm))

    # LLM property linking (after LLMIndividual, needs resolved classes)
    config.post_parallel.append(LLMPropertyStage(llm=property_llm))

    if classifier_llm is not None or extractor_llm is not None:
        config.post_parallel.append(
            MetadataStage(
                classifier_llm or extractor_llm,
                classifier_llm=classifier_llm,
                extractor_llm=extractor_llm,
            )
        )

    config.post_parallel.append(DependencyStage())

    return config


def build_stages(
    llm: LLMProvider | None = None,
    task_llms: TaskLLMs | None = None,
) -> list[PipelineStage]:
    """Build the full pipeline stage list.

    When *task_llms* is provided, each stage uses its task-specific LLM.
    Otherwise the single *llm* is used for all stages (backward-compatible).
    LLM-dependent stages are included only when an LLM provider is available;
    otherwise they are skipped gracefully.
    """
    embedding_service = _get_embedding_service()

    concept_llm = (task_llms.concept if task_llms else llm) or llm
    branch_judge_llm = (task_llms.branch_judge if task_llms else llm) or llm
    classifier_llm = (task_llms.classifier if task_llms else llm) or llm
    extractor_llm = (task_llms.extractor if task_llms else llm) or llm
    individual_llm = (task_llms.individual if task_llms else llm) or llm
    property_llm = (task_llms.property_llm if task_llms else llm) or llm
    document_type_llm = (task_llms.document_type if task_llms else llm) or llm

    stages: list[PipelineStage] = [
        IngestionStage(),
        NormalizationStage(),
        EntityRulerStage(embedding_service=embedding_service),
    ]

    # Early individual extraction (citations + regex/spaCy) — fast, no LLM
    stages.append(EarlyIndividualStage())

    # Early property extraction (Aho-Corasick) — fast, no LLM
    stages.append(EarlyPropertyStage())

    # Early document type classification — LLM-based
    if document_type_llm is not None:
        stages.append(DocumentTypeStage(document_type_llm))

    if concept_llm is not None:
        stages.append(LLMConceptStage(concept_llm))

    stages.append(ReconciliationStage(embedding_service=embedding_service))
    stages.append(ResolutionStage(embedding_service=embedding_service))

    if concept_llm is not None:
        stages.append(ContextualRerankStage(concept_llm))

    if branch_judge_llm is not None:
        stages.append(BranchJudgeStage(branch_judge_llm))

    stages.append(StringMatchStage())

    # LLM individual linking (after StringMatch, needs resolved classes)
    stages.append(LLMIndividualStage(llm=individual_llm))

    # LLM property linking (after LLMIndividual, needs resolved classes)
    stages.append(LLMPropertyStage(llm=property_llm))

    if classifier_llm is not None or extractor_llm is not None:
        stages.append(
            MetadataStage(
                classifier_llm or extractor_llm,
                classifier_llm=classifier_llm,
                extractor_llm=extractor_llm,
            )
        )

    stages.append(DependencyStage())

    return stages


def _make_llm(provider_name: str, model: str) -> LLMProvider | None:
    """Create an LLM provider from a provider name and model string.

    Returns None if the provider is unknown or no API key is available.
    """
    from app.models.llm_models import LLMProviderType
    from app.services.llm.registry import REQUIRES_API_KEY, get_provider
    from app.api.routes.settings import _get_api_key_for_provider

    normalized = provider_name.replace("-", "_")
    if normalized == "lm_studio":
        normalized = "lmstudio"

    try:
        provider_type = LLMProviderType(normalized)
    except ValueError:
        logger.warning("Unknown LLM provider %s", provider_name)
        return None

    api_key = _get_api_key_for_provider(provider_type)

    if REQUIRES_API_KEY.get(provider_type, True) and not api_key:
        logger.warning("No API key for %s", provider_type.value)
        return None

    return get_provider(
        provider_type=provider_type,
        api_key=api_key,
        model=model or None,
    )


def _try_get_llm() -> LLMProvider | None:
    """Try to create an LLM provider from global settings. Returns None if no API key."""
    try:
        from app.config import settings
        return _make_llm(settings.llm_provider, settings.llm_model)
    except Exception:
        logger.warning("Failed to create LLM provider — LLM stages will be skipped", exc_info=True)
        return None


def _try_get_task_llm(task: str, fallback: LLMProvider | None) -> LLMProvider | None:
    """Get a task-specific LLM, falling back to *fallback* (the global default).

    Reads ``llm_{task}_provider`` and ``llm_{task}_model`` from settings.
    If neither is set, returns *fallback* unchanged.
    """
    from app.config import settings

    task_provider = getattr(settings, f"llm_{task}_provider", "")
    task_model = getattr(settings, f"llm_{task}_model", "")

    if not task_provider:
        return fallback

    try:
        llm = _make_llm(task_provider, task_model)
        if llm is not None:
            logger.info("Using task-specific LLM for %s: %s/%s", task, task_provider, task_model)
            return llm
    except Exception:
        logger.warning("Failed to create task-specific LLM for %s — using global default", task, exc_info=True)

    return fallback


def _log_activity(job: Job, stage: str, msg: str) -> None:
    """Append an activity log entry to job metadata."""
    log = job.result.metadata.setdefault("activity_log", [])
    log.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "msg": msg,
    })


class PipelineOrchestrator:
    def __init__(
        self,
        job_store: JobStore,
        stages: list[PipelineStage] | None = None,
        llm: LLMProvider | None = None,
        task_llms: TaskLLMs | None = None,
    ) -> None:
        self.job_store = job_store
        self._llm = llm
        self._task_llms = task_llms
        self._config: PipelineConfig | None = None
        if stages is not None:
            # Legacy flat mode: use stages list directly
            self.stages = stages
        else:
            # New parallel mode: build PipelineConfig
            self._config = build_pipeline_config(llm, task_llms=task_llms)
            self.stages = build_stages(llm, task_llms=task_llms)  # kept for backward compat

    async def run(self, job: Job) -> Job:
        if self._config is not None:
            return await self._run_parallel(job)
        return await self._run_flat(job)

    async def _run_parallel(self, job: Job) -> Job:
        """Three-phase pipeline: pre-parallel → parallel(EntityRuler ∥ LLM) → post-parallel."""
        config = self._config
        assert config is not None

        try:
            # Phase 1: Sequential pre-parallel stages (Ingestion, Normalization)
            for stage in config.pre_parallel:
                logger.info("Running stage %s for job %s", stage.name, job.id)
                try:
                    job = await stage.execute(job)
                except Exception as stage_err:
                    logger.warning(
                        "Stage %s failed for job %s: %s — continuing",
                        stage.name, job.id, stage_err,
                    )
                    continue
                job.updated_at = datetime.now(timezone.utc)
                await self.job_store.save(job)

            _log_activity(job, "orchestrator", "Ingestion and normalization complete")

            # Phase 2: Parallel EntityRuler and LLM
            job.status = JobStatus.ENRICHING
            job.updated_at = datetime.now(timezone.utc)
            await self.job_store.save(job)

            _log_activity(job, "orchestrator", "Running EntityRuler, LLM, early individuals, early properties, and document type in parallel...")

            async def run_entity_ruler(j: Job) -> None:
                if config.entity_ruler is None:
                    return
                logger.info("Running stage %s for job %s (parallel)", config.entity_ruler.name, j.id)
                try:
                    await config.entity_ruler.execute(j)
                    j.updated_at = datetime.now(timezone.utc)
                    await self.job_store.save(j)
                except Exception as e:
                    logger.warning("Stage %s failed for job %s: %s — continuing",
                                   config.entity_ruler.name, j.id, e)

            async def run_llm_concept(j: Job) -> None:
                if config.llm_concept is None:
                    return
                logger.info("Running stage %s for job %s (parallel)", config.llm_concept.name, j.id)
                try:
                    await config.llm_concept.execute(j)
                    j.updated_at = datetime.now(timezone.utc)
                    await self.job_store.save(j)
                except Exception as e:
                    logger.warning("Stage %s failed for job %s: %s — continuing",
                                   config.llm_concept.name, j.id, e)

            async def run_early_individual(j: Job) -> None:
                if config.early_individual is None:
                    return
                logger.info("Running stage %s for job %s (parallel)", config.early_individual.name, j.id)
                try:
                    await config.early_individual.execute(j)
                    j.updated_at = datetime.now(timezone.utc)
                    await self.job_store.save(j)
                except Exception as e:
                    logger.warning("Stage %s failed for job %s: %s — continuing",
                                   config.early_individual.name, j.id, e)

            async def run_early_property(j: Job) -> None:
                if config.early_property is None:
                    return
                logger.info("Running stage %s for job %s (parallel)", config.early_property.name, j.id)
                try:
                    await config.early_property.execute(j)
                    j.updated_at = datetime.now(timezone.utc)
                    await self.job_store.save(j)
                except Exception as e:
                    logger.warning("Stage %s failed for job %s: %s — continuing",
                                   config.early_property.name, j.id, e)

            async def run_document_type(j: Job) -> None:
                if config.document_type is None:
                    return
                logger.info("Running stage %s for job %s (parallel)", config.document_type.name, j.id)
                try:
                    await config.document_type.execute(j)
                    j.updated_at = datetime.now(timezone.utc)
                    await self.job_store.save(j)
                except Exception as e:
                    logger.warning("Stage %s failed for job %s: %s — continuing",
                                   config.document_type.name, j.id, e)

            await asyncio.gather(
                run_entity_ruler(job),
                run_llm_concept(job),
                run_early_individual(job),
                run_early_property(job),
                run_document_type(job),
            )

            _log_activity(job, "orchestrator", "Parallel enrichment complete")

            # Phase 3: Sequential post-parallel stages
            for stage in config.post_parallel:
                logger.info("Running stage %s for job %s", stage.name, job.id)
                try:
                    job = await stage.execute(job)
                except Exception as stage_err:
                    logger.warning(
                        "Stage %s failed for job %s: %s — continuing",
                        stage.name, job.id, stage_err,
                    )
                    continue
                job.updated_at = datetime.now(timezone.utc)
                await self.job_store.save(job)

            _log_activity(job, "orchestrator", f"Pipeline complete \u2014 {len(job.result.annotations)} annotations, {len(job.result.properties)} properties")
            job.status = JobStatus.COMPLETED
            job.updated_at = datetime.now(timezone.utc)
            await self.job_store.save(job)

            # Post-completion: Area of Law assessment (runs after pipeline results are available)
            aol_llm = (self._task_llms.area_of_law if self._task_llms else None) or self._llm
            if aol_llm is not None:
                try:
                    from app.services.concept.area_of_law_assessor import AreaOfLawAssessor
                    assessor = AreaOfLawAssessor(aol_llm)
                    areas = await assessor.assess(job)
                    job.result.metadata["areas_of_law"] = areas
                    _log_activity(job, "area_of_law",
                        f"Classified: {', '.join(a['area'] for a in areas)}")
                    await self.job_store.save(job)
                except Exception as e:
                    logger.warning("Area of law assessment failed: %s", e)

            # Post-completion: Document type quality cross-check
            dt_llm = (self._task_llms.document_type if self._task_llms else None) or self._llm
            if dt_llm is not None and job.result.metadata.get("self_identified_type"):
                try:
                    from app.services.quality.document_type_checker import DocumentTypeChecker
                    checker = DocumentTypeChecker(dt_llm)
                    signals = await checker.check(job)
                    if signals:
                        job.result.metadata["quality_signals"] = signals
                        _log_activity(job, "quality_check",
                            f"Document type cross-check: {len(signals)} signal(s)")
                        await self.job_store.save(job)
                except Exception as e:
                    logger.warning("Document type quality check failed: %s", e)

        except Exception as e:
            logger.exception("Pipeline failed for job %s", job.id)
            _log_activity(job, "orchestrator", f"Pipeline failed: {e}")
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.updated_at = datetime.now(timezone.utc)
            await self.job_store.save(job)

        return job

    async def _run_flat(self, job: Job) -> Job:
        """Legacy sequential pipeline for backward compatibility with stages= parameter."""
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
                    continue
                job.updated_at = datetime.now(timezone.utc)
                await self.job_store.save(job)

            job.status = JobStatus.COMPLETED
            job.updated_at = datetime.now(timezone.utc)
            await self.job_store.save(job)

            # Post-completion: Area of Law assessment (runs after pipeline results are available)
            aol_llm = (self._task_llms.area_of_law if self._task_llms else None) or self._llm
            if aol_llm is not None:
                try:
                    from app.services.concept.area_of_law_assessor import AreaOfLawAssessor
                    assessor = AreaOfLawAssessor(aol_llm)
                    areas = await assessor.assess(job)
                    job.result.metadata["areas_of_law"] = areas
                    _log_activity(job, "area_of_law",
                        f"Classified: {', '.join(a['area'] for a in areas)}")
                    await self.job_store.save(job)
                except Exception as e:
                    logger.warning("Area of law assessment failed: %s", e)

            # Post-completion: Document type quality cross-check
            dt_llm = (self._task_llms.document_type if self._task_llms else None) or self._llm
            if dt_llm is not None and job.result.metadata.get("self_identified_type"):
                try:
                    from app.services.quality.document_type_checker import DocumentTypeChecker
                    checker = DocumentTypeChecker(dt_llm)
                    signals = await checker.check(job)
                    if signals:
                        job.result.metadata["quality_signals"] = signals
                        _log_activity(job, "quality_check",
                            f"Document type cross-check: {len(signals)} signal(s)")
                        await self.job_store.save(job)
                except Exception as e:
                    logger.warning("Document type quality check failed: %s", e)

        except Exception as e:
            logger.exception("Pipeline failed for job %s", job.id)
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.updated_at = datetime.now(timezone.utc)
            await self.job_store.save(job)

        return job
