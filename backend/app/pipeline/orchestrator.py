from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.pipeline.stages.ingestion_stage import IngestionStage
from app.pipeline.stages.normalization_stage import NormalizationStage
from app.storage.job_store import JobStore

logger = logging.getLogger(__name__)


def default_stages() -> list[PipelineStage]:
    return [IngestionStage(), NormalizationStage()]


class PipelineOrchestrator:
    def __init__(
        self,
        job_store: JobStore,
        stages: list[PipelineStage] | None = None,
    ) -> None:
        self.job_store = job_store
        self.stages = stages if stages is not None else default_stages()

    async def run(self, job: Job) -> Job:
        try:
            for stage in self.stages:
                logger.info("Running stage %s for job %s", stage.name, job.id)
                job = await stage.execute(job)
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
