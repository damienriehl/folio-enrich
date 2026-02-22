from __future__ import annotations

from app.models.annotation import ConceptMatch
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.folio.resolver import ConceptResolver


class ResolutionStage(PipelineStage):
    def __init__(self, resolver: ConceptResolver | None = None) -> None:
        self.resolver = resolver or ConceptResolver()

    @property
    def name(self) -> str:
        return "resolution"

    async def execute(self, job: Job) -> Job:
        job.status = JobStatus.RESOLVING

        # Gather all concepts from LLM (and later EntityRuler) results
        llm_concepts = job.result.metadata.get("llm_concepts", {})
        resolved_concepts: list[dict] = []

        for chunk_idx, concepts in llm_concepts.items():
            for concept_data in concepts:
                resolved = self.resolver.resolve(
                    concept_text=concept_data.get("concept_text", ""),
                    branch=concept_data.get("branch", ""),
                    confidence=concept_data.get("confidence", 0.0),
                    source=concept_data.get("source", "llm"),
                )
                if resolved:
                    resolved_concepts.append({
                        "concept_text": resolved.concept_text,
                        "folio_iri": resolved.folio_concept.iri,
                        "folio_label": resolved.folio_concept.preferred_label,
                        "folio_definition": resolved.folio_concept.definition,
                        "branch": resolved.branch,
                        "confidence": resolved.confidence,
                        "source": resolved.source,
                    })

        job.result.metadata["resolved_concepts"] = resolved_concepts
        return job
