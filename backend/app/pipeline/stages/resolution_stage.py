from __future__ import annotations

import logging

from app.models.annotation import ConceptMatch
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.folio.resolver import ConceptResolver

logger = logging.getLogger(__name__)


class ResolutionStage(PipelineStage):
    def __init__(self, resolver: ConceptResolver | None = None) -> None:
        self.resolver = resolver or ConceptResolver()

    @property
    def name(self) -> str:
        return "resolution"

    async def execute(self, job: Job) -> Job:
        job.status = JobStatus.RESOLVING

        # Prefer reconciled concepts (merged ruler + LLM); fall back to individual sources
        reconciled = job.result.metadata.get("reconciled_concepts", [])
        resolved_concepts: list[dict] = []

        if reconciled:
            for concept_data in reconciled:
                resolved = self.resolver.resolve(
                    concept_text=concept_data.get("concept_text", ""),
                    branch=concept_data.get("branch", ""),
                    confidence=concept_data.get("confidence", 0.0),
                    source=concept_data.get("source", "reconciled"),
                    folio_iri=concept_data.get("folio_iri"),  # Use IRI directly
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
        else:
            # No reconciled concepts — resolve from individual sources
            ruler_raw = job.result.metadata.get("ruler_concepts", [])
            for concept_data in ruler_raw:
                resolved = self.resolver.resolve(
                    concept_text=concept_data.get("concept_text", ""),
                    branch=concept_data.get("branch", ""),
                    confidence=concept_data.get("confidence", 1.0),
                    source="entity_ruler",
                    folio_iri=concept_data.get("folio_iri"),  # Use IRI directly
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

            # Then LLM concepts
            llm_concepts = job.result.metadata.get("llm_concepts", {})
            seen_texts = {c["concept_text"].lower() for c in resolved_concepts}
            for chunk_idx, concepts in llm_concepts.items():
                for concept_data in concepts:
                    ct = concept_data.get("concept_text", "").lower()
                    if ct in seen_texts:
                        continue
                    seen_texts.add(ct)
                    resolved = self.resolver.resolve(
                        concept_text=concept_data.get("concept_text", ""),
                        branch=concept_data.get("branch", ""),
                        confidence=concept_data.get("confidence", 0.0),
                        source="llm",
                        folio_iri=concept_data.get("folio_iri"),
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
        logger.info("Resolved %d concepts for job %s", len(resolved_concepts), job.id)
        return job
