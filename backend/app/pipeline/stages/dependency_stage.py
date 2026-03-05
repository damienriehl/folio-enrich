"""TripleEnrichmentStage — cross-links existing triples to FOLIO entities.

Runs post-parallel after LLMProperty. Enriches triples produced by
EarlyTripleStage with links to Individuals, Concepts (Annotations),
and Properties. Also writes backward-compatible metadata["spo_triples"].
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.annotation import TripleLink
from app.models.job import Job
from app.pipeline.stages.base import PipelineStage


class TripleEnrichmentStage(PipelineStage):
    @property
    def name(self) -> str:
        return "triple_enrichment"

    async def execute(self, job: Job) -> Job:
        if not job.result.triples:
            return job

        for triple in job.result.triples:
            # Link subject/object to Individuals
            self._link_individuals(triple, job)
            # Link subject/object to Concept annotations
            self._link_concepts(triple, job)
            # Link predicate to Properties
            self._link_properties(triple, job)

        # Backward-compatible metadata
        job.result.metadata["spo_triples"] = []
        for t in job.result.triples:
            triple_dict = {
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
                "sentence": t.sentence,
                "voice": t.voice,
                "normalized": t.normalized,
                "subject_iri": "",
                "object_iri": "",
            }
            # Pull first concept link IRI if available
            for link in t.subject_links:
                if link.entity_type == "concept" and link.folio_iri:
                    triple_dict["subject_iri"] = link.folio_iri
                    break
            for link in t.object_links:
                if link.entity_type == "concept" and link.folio_iri:
                    triple_dict["object_iri"] = link.folio_iri
                    break
            # Individual enrichments
            for link in t.subject_links:
                if link.entity_type == "individual":
                    triple_dict["subject_individual"] = {
                        "id": link.entity_id,
                        "folio_label": link.folio_label,
                    }
                    break
            for link in t.object_links:
                if link.entity_type == "individual":
                    triple_dict["object_individual"] = {
                        "id": link.entity_id,
                        "folio_label": link.folio_label,
                    }
                    break
            # Property enrichments
            for link in t.predicate_links:
                if link.entity_type == "property":
                    triple_dict["predicate_property"] = {
                        "id": link.entity_id,
                        "folio_iri": link.folio_iri,
                        "folio_label": link.folio_label,
                    }
                    break
            job.result.metadata["spo_triples"].append(triple_dict)

        linked_count = sum(
            1 for t in job.result.triples
            if t.subject_links or t.object_links or t.predicate_links
        )

        log = job.result.metadata.setdefault("activity_log", [])
        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": f"Enriched {len(job.result.triples)} triples ({linked_count} FOLIO-linked)",
        })

        return job

    def _link_individuals(self, triple, job: Job) -> None:
        """Match subject/object text to Individual mention_text."""
        for ind in job.result.individuals:
            mention = ind.mention_text.lower()
            if not mention:
                continue
            if mention in triple.subject.lower():
                triple.subject_links.append(TripleLink(
                    entity_type="individual",
                    entity_id=ind.id,
                    folio_label=ind.name,
                    confidence=0.8,
                ))
            if mention in triple.object.lower():
                triple.object_links.append(TripleLink(
                    entity_type="individual",
                    entity_id=ind.id,
                    folio_label=ind.name,
                    confidence=0.8,
                ))

    def _link_concepts(self, triple, job: Job) -> None:
        """Match subject/object spans to Annotation spans."""
        if not triple.subject_span or not triple.object_span:
            return

        for ann in job.result.annotations:
            if ann.state == "rejected" or not ann.concepts:
                continue
            concept = ann.concepts[0]
            ann_start = ann.span.start
            ann_end = ann.span.end

            # Check subject overlap
            if (triple.subject_span.start <= ann_end and
                    triple.subject_span.end >= ann_start):
                triple.subject_links.append(TripleLink(
                    entity_type="concept",
                    entity_id=ann.id,
                    folio_iri=concept.folio_iri,
                    folio_label=concept.folio_label,
                    confidence=concept.confidence,
                ))

            # Check object overlap
            if (triple.object_span.start <= ann_end and
                    triple.object_span.end >= ann_start):
                triple.object_links.append(TripleLink(
                    entity_type="concept",
                    entity_id=ann.id,
                    folio_iri=concept.folio_iri,
                    folio_label=concept.folio_label,
                    confidence=concept.confidence,
                ))

    def _link_properties(self, triple, job: Job) -> None:
        """Match predicate text to PropertyAnnotation labels."""
        pred_lower = triple.predicate.lower()
        for prop in job.result.properties:
            prop_text = prop.property_text.lower()
            if prop_text and prop_text in pred_lower:
                triple.predicate_links.append(TripleLink(
                    entity_type="property",
                    entity_id=prop.id,
                    folio_iri=prop.folio_iri,
                    folio_label=prop.folio_label,
                    confidence=prop.confidence,
                ))


# Backward-compatible alias
DependencyStage = TripleEnrichmentStage
