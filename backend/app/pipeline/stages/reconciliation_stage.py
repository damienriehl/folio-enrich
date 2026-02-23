from __future__ import annotations

from datetime import datetime, timezone

from app.models.annotation import ConceptMatch
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.reconciliation.reconciler import Reconciler


class ReconciliationStage(PipelineStage):
    def __init__(self, reconciler: Reconciler | None = None, embedding_service=None) -> None:
        self.reconciler = reconciler or Reconciler(embedding_service=embedding_service)

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

        # Use embedding triage if embedding service is available
        if self.reconciler._embedding_service is not None:
            results = self.reconciler.reconcile_with_embedding_triage(ruler_concepts, llm_concepts)
        else:
            results = self.reconciler.reconcile(ruler_concepts, llm_concepts)

        # Store reconciled concepts for resolution stage (all start as "preliminary")
        reconciled = [
            {
                "concept_text": r.concept.concept_text,
                "branch": r.concept.branch or "",
                "confidence": r.concept.confidence,
                "source": r.concept.source,
                "folio_iri": r.concept.folio_iri,
                "category": r.category,
                "state": "preliminary",
            }
            for r in results
        ]
        job.result.metadata["reconciled_concepts"] = reconciled

        # Update preliminary annotation states based on reconciliation results
        reconciled_by_text = {}
        for r in results:
            reconciled_by_text[r.concept.concept_text.lower()] = r.category

        for ann in job.result.annotations:
            if ann.state != "preliminary":
                continue
            concept_text = ann.concepts[0].concept_text.lower() if ann.concepts else ""
            category = reconciled_by_text.get(concept_text)
            if category in ("both_agree", "conflict_resolved"):
                ann.state = "confirmed"
            elif category is None:
                # Not in reconciled set — low confidence, filtered out
                ann.state = "rejected"
            # "ruler_only" stays as "preliminary" (confirmed later by resolution)

        confirmed = sum(1 for a in job.result.annotations if a.state == "confirmed")
        ruler_only = sum(1 for r in results if r.category == "ruler_only")
        rejected = sum(1 for a in job.result.annotations if a.state == "rejected")
        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"Reconciled: {confirmed} confirmed, {ruler_only} ruler-only, {rejected} rejected"})
        return job
