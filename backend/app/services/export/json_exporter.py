from __future__ import annotations

import json

from app.models.job import Job
from app.services.export.base import ExporterBase


class JSONExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "json"

    @property
    def content_type(self) -> str:
        return "application/json"

    def export(self, job: Job) -> str:
        output = {
            "job_id": str(job.id),
            "status": job.status.value,
            "document": {
                "format": job.input.format.value if job.input else None,
                "filename": job.input.filename if job.input else None,
            },
            "metadata": {
                k: v
                for k, v in (job.result.metadata or {}).items()
                if not k.startswith("_")
            },
            "annotations": [
                {
                    "span": {
                        "start": a.span.start,
                        "end": a.span.end,
                        "text": a.span.text,
                    },
                    "concepts": [
                        {
                            k: v
                            for k, v in {
                                "concept_text": c.concept_text,
                                "folio_iri": c.folio_iri,
                                "folio_label": c.folio_label,
                                "folio_definition": c.folio_definition,
                                "branch": c.branches[0] if c.branches else "",
                                "branches": c.branches,
                                "confidence": c.confidence,
                                "source": c.source,
                                "folio_examples": c.folio_examples or None,
                                "folio_alt_labels": c.folio_alt_labels or None,
                                "folio_see_also": c.folio_see_also or None,
                                "folio_source": c.folio_source or None,
                            }.items()
                            if v is not None
                        }
                        for c in a.concepts
                    ],
                }
                for a in job.result.annotations
            ],
            "individuals": [
                {
                    "id": ind.id,
                    "name": ind.name,
                    "mention_text": ind.mention_text,
                    "individual_type": ind.individual_type,
                    "span": {
                        "start": ind.span.start,
                        "end": ind.span.end,
                        "text": ind.span.text,
                    },
                    "class_links": [
                        {
                            k: v
                            for k, v in {
                                "annotation_id": cl.annotation_id,
                                "folio_iri": cl.folio_iri,
                                "folio_label": cl.folio_label,
                                "branch": cl.branch,
                                "relationship": cl.relationship,
                                "confidence": cl.confidence,
                            }.items()
                            if v
                        }
                        for cl in ind.class_links
                    ],
                    "confidence": ind.confidence,
                    "source": ind.source,
                    **({"normalized_form": ind.normalized_form} if ind.normalized_form else {}),
                    **({"url": ind.url} if ind.url else {}),
                }
                for ind in job.result.individuals
            ],
            "properties": [
                {
                    k: v
                    for k, v in {
                        "id": prop.id,
                        "property_text": prop.property_text,
                        "folio_iri": prop.folio_iri,
                        "folio_label": prop.folio_label,
                        "folio_definition": prop.folio_definition or None,
                        "folio_examples": prop.folio_examples or None,
                        "folio_alt_labels": prop.folio_alt_labels or None,
                        "domain_iris": prop.domain_iris or None,
                        "range_iris": prop.range_iris or None,
                        "inverse_of_iri": prop.inverse_of_iri or None,
                        "span": {
                            "start": prop.span.start,
                            "end": prop.span.end,
                            "text": prop.span.text,
                        },
                        "confidence": prop.confidence,
                        "source": prop.source,
                        "match_type": prop.match_type,
                    }.items()
                    if v is not None
                }
                for prop in job.result.properties
            ],
            "statistics": {
                "total_annotations": len(job.result.annotations),
                "unique_concepts": len(
                    {
                        c.folio_iri
                        for a in job.result.annotations
                        for c in a.concepts
                        if c.folio_iri
                    }
                ),
                "total_individuals": len(job.result.individuals),
                "legal_citations": len(
                    [i for i in job.result.individuals if i.individual_type == "legal_citation"]
                ),
                "named_entities": len(
                    [i for i in job.result.individuals if i.individual_type == "named_entity"]
                ),
                "total_properties": len(job.result.properties),
                "unique_properties": len(
                    {p.folio_iri for p in job.result.properties if p.folio_iri}
                ),
            },
        }
        return json.dumps(output, indent=2)
