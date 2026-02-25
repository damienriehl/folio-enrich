from __future__ import annotations

from datetime import datetime, timezone

from app.models.job import Job
from app.pipeline.stages.base import PipelineStage
from app.services.dependency.parser import DependencyParser


class DependencyStage(PipelineStage):
    def __init__(self, parser: DependencyParser | None = None) -> None:
        self.parser = parser or DependencyParser()

    @property
    def name(self) -> str:
        return "dependency_parsing"

    async def execute(self, job: Job) -> Job:
        if job.result.canonical_text is None or not job.result.annotations:
            return job

        concept_spans = []
        for ann in job.result.annotations:
            if ann.concepts:
                concept_spans.append({
                    "text": ann.span.text,
                    "start": ann.span.start,
                    "end": ann.span.end,
                    "iri": ann.concepts[0].folio_iri or "",
                })

        triples = self.parser.extract_triples(
            job.result.canonical_text.full_text, concept_spans
        )

        job.result.metadata["spo_triples"] = []
        for t in triples:
            triple_dict = {
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
                "sentence": t.sentence,
                "subject_iri": t.subject_iri,
                "object_iri": t.object_iri,
            }

            # Enrich with individual references
            for ind in job.result.individuals:
                mention = ind.mention_text.lower()
                if mention and mention in t.subject.lower():
                    triple_dict["subject_individual"] = {
                        "id": ind.id,
                        "name": ind.name,
                        "individual_type": ind.individual_type,
                    }
                    break
            for ind in job.result.individuals:
                mention = ind.mention_text.lower()
                if mention and mention in t.object.lower():
                    triple_dict["object_individual"] = {
                        "id": ind.id,
                        "name": ind.name,
                        "individual_type": ind.individual_type,
                    }
                    break

            # Enrich predicate with FOLIO property IRI
            pred_lower = t.predicate.lower()
            for prop in job.result.properties:
                prop_text = prop.property_text.lower()
                if prop_text and prop_text in pred_lower:
                    triple_dict["predicate_property"] = {
                        "id": prop.id,
                        "folio_iri": prop.folio_iri,
                        "folio_label": prop.folio_label,
                    }
                    break

            job.result.metadata["spo_triples"].append(triple_dict)

        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"Extracted {len(triples)} subject-predicate-object triples"})
        return job
