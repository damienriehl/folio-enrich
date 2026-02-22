from __future__ import annotations

from app.models.annotation import ConceptMatch
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.reconciliation.reconciler import Reconciler


class ReconciliationStage(PipelineStage):
    def __init__(self, reconciler: Reconciler | None = None) -> None:
        self.reconciler = reconciler or Reconciler()

    @property
    def name(self) -> str:
        return "reconciliation"

    async def execute(self, job: Job) -> Job:
        # Gather ruler concepts
        ruler_raw = job.result.metadata.get("ruler_concepts", [])
        ruler_concepts = [ConceptMatch(**c) for c in ruler_raw]

        # Gather LLM concepts (flatten from per-chunk)
        llm_raw = job.result.metadata.get("llm_concepts", {})
        llm_concepts = []
        for chunk_concepts in llm_raw.values():
            for c in chunk_concepts:
                llm_concepts.append(ConceptMatch(**c))

        results = self.reconciler.reconcile(ruler_concepts, llm_concepts)

        # Store reconciled concepts for resolution stage
        reconciled = [
            {
                "concept_text": r.concept.concept_text,
                "branch": r.concept.branch or "",
                "confidence": r.concept.confidence,
                "source": r.concept.source,
                "folio_iri": r.concept.folio_iri,
                "category": r.category,
            }
            for r in results
        ]
        job.result.metadata["reconciled_concepts"] = reconciled
        return job
