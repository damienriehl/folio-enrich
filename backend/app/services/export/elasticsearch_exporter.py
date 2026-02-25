from __future__ import annotations

import json

from app.models.job import Job
from app.services.export.base import ExporterBase


class ElasticsearchExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "elasticsearch"

    @property
    def content_type(self) -> str:
        return "application/x-ndjson"

    def export(self, job: Job) -> str:
        lines = []
        for ann in job.result.annotations:
            for concept in ann.concepts:
                # Bulk API action
                action = {"index": {"_index": "folio-annotations"}}
                lines.append(json.dumps(action))
                # Document
                doc = {
                    "job_id": str(job.id),
                    "span_start": ann.span.start,
                    "span_end": ann.span.end,
                    "span_text": ann.span.text,
                    "concept_text": concept.concept_text,
                    "folio_iri": concept.folio_iri,
                    "folio_label": concept.folio_label,
                    "branch": concept.branches[0] if concept.branches else "",
                    "branches": concept.branches,
                    "confidence": concept.confidence,
                    "source": concept.source,
                    "document_type": job.result.metadata.get("document_type", ""),
                }
                lines.append(json.dumps(doc))

        # Individual documents
        for ind in job.result.individuals:
            action = {"index": {"_index": "folio-individuals"}}
            lines.append(json.dumps(action))
            doc = {
                "job_id": str(job.id),
                "individual_id": ind.id,
                "name": ind.name,
                "mention_text": ind.mention_text,
                "individual_type": ind.individual_type,
                "span_start": ind.span.start,
                "span_end": ind.span.end,
                "class_links": [
                    {
                        "folio_iri": cl.folio_iri,
                        "folio_label": cl.folio_label,
                        "confidence": cl.confidence,
                    }
                    for cl in ind.class_links
                ],
                "confidence": ind.confidence,
                "source": ind.source,
            }
            if ind.normalized_form:
                doc["normalized_form"] = ind.normalized_form
            if ind.url:
                doc["url"] = ind.url
            lines.append(json.dumps(doc))

        # Property documents
        for prop in job.result.properties:
            action = {"index": {"_index": "folio-properties"}}
            lines.append(json.dumps(action))
            doc = {
                "job_id": str(job.id),
                "property_id": prop.id,
                "property_text": prop.property_text,
                "folio_iri": prop.folio_iri,
                "folio_label": prop.folio_label,
                "span_start": prop.span.start,
                "span_end": prop.span.end,
                "confidence": prop.confidence,
                "source": prop.source,
                "match_type": prop.match_type,
            }
            if prop.domain_iris:
                doc["domain_iris"] = prop.domain_iris
            if prop.range_iris:
                doc["range_iris"] = prop.range_iris
            if prop.inverse_of_iri:
                doc["inverse_of_iri"] = prop.inverse_of_iri
            lines.append(json.dumps(doc))

        return "\n".join(lines) + "\n" if lines else ""
