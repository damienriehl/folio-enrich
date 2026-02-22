from __future__ import annotations

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.ingestion import registry as ingestion


class IngestionStage(PipelineStage):
    @property
    def name(self) -> str:
        return "ingestion"

    async def execute(self, job: Job) -> Job:
        job.status = JobStatus.INGESTING
        raw_text, elements = ingestion.ingest_with_elements(job.input)
        # Store raw text temporarily for next stage
        job.result.metadata["_raw_text"] = raw_text
        # Store text elements for structural tracking
        if elements:
            job.result.metadata["_text_elements"] = [e.model_dump() for e in elements]
        return job
