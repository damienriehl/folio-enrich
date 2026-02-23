from __future__ import annotations

from datetime import datetime, timezone

from app.models.document import TextElement
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

        # Attach text elements from ingestion if available
        elements_raw = job.result.metadata.pop("_text_elements", [])
        if elements_raw:
            canonical.elements = [TextElement(**e) for e in elements_raw]

        job.result.canonical_text = canonical

        log = job.result.metadata.setdefault("activity_log", [])
        n_chunks = len(canonical.chunks)
        n_sentences = len(canonical.sentences)
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"Normalized into {n_chunks} chunks, {n_sentences} sentences"})
        return job
