from __future__ import annotations

from app.models.annotation import ConceptMatch
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.entity_ruler.ruler import FOLIOEntityRuler


class EntityRulerStage(PipelineStage):
    def __init__(self, ruler: FOLIOEntityRuler | None = None) -> None:
        self.ruler = ruler or FOLIOEntityRuler()

    @property
    def name(self) -> str:
        return "entity_ruler"

    async def execute(self, job: Job) -> Job:
        if job.result.canonical_text is None:
            return job

        matches = self.ruler.find_matches(job.result.canonical_text.full_text)

        ruler_concepts = []
        for match in matches:
            ruler_concepts.append(
                ConceptMatch(
                    concept_text=match.text,
                    folio_iri=match.entity_id,
                    confidence=1.0,  # Deterministic match
                    source="entity_ruler",
                ).model_dump()
            )

        job.result.metadata["ruler_concepts"] = ruler_concepts
        return job
