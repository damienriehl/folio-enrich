from __future__ import annotations

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.concept.llm_concept_identifier import LLMConceptIdentifier
from app.services.llm.base import LLMProvider


class LLMConceptStage(PipelineStage):
    def __init__(self, llm: LLMProvider) -> None:
        self.identifier = LLMConceptIdentifier(llm)

    @property
    def name(self) -> str:
        return "llm_concept_identification"

    async def execute(self, job: Job) -> Job:
        job.status = JobStatus.IDENTIFYING
        if job.result.canonical_text is None:
            return job

        chunks = job.result.canonical_text.chunks
        results = await self.identifier.identify_concepts_batch(chunks)

        # Store raw LLM concepts in metadata for later reconciliation
        job.result.metadata["llm_concepts"] = {
            str(k): [c.model_dump() for c in v] for k, v in results.items()
        }

        from datetime import datetime, timezone
        total = sum(len(v) for v in results.values())
        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"LLM extracted {total} concepts from {len(chunks)} chunks"})
        return job
