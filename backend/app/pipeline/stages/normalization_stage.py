from __future__ import annotations

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.normalization.normalizer import normalize_and_chunk


class NormalizationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "normalization"

    async def execute(self, job: Job) -> Job:
        job.status = JobStatus.NORMALIZING
        raw_text = job.result.metadata.pop("_raw_text", "")
        canonical = normalize_and_chunk(raw_text, job.input.format)
        job.result.canonical_text = canonical
        return job
