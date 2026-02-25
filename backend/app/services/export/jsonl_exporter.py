from __future__ import annotations

import json

from app.models.job import Job
from app.services.export.base import ExporterBase


class JSONLExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "jsonl"

    @property
    def content_type(self) -> str:
        return "application/jsonl"

    def export(self, job: Job) -> str:
        lines = []
        for ann in job.result.annotations:
            record = {
                "span_start": ann.span.start,
                "span_end": ann.span.end,
                "span_text": ann.span.text,
                "concepts": [
                    {
                        "concept_text": c.concept_text,
                        "folio_iri": c.folio_iri,
                        "folio_label": c.folio_label,
                        "branch": c.branches[0] if c.branches else "",
                        "branches": c.branches,
                        "confidence": c.confidence,
                        "source": c.source,
                    }
                    for c in ann.concepts
                ],
            }
            lines.append(json.dumps(record))
        # Individual records
        for ind in job.result.individuals:
            record = {
                "record_type": "individual",
                "id": ind.id,
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
                record["normalized_form"] = ind.normalized_form
            if ind.url:
                record["url"] = ind.url
            lines.append(json.dumps(record))

        # Property records
        for prop in job.result.properties:
            record = {
                "record_type": "property",
                "id": prop.id,
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
                record["domain_iris"] = prop.domain_iris
            if prop.range_iris:
                record["range_iris"] = prop.range_iris
            if prop.inverse_of_iri:
                record["inverse_of_iri"] = prop.inverse_of_iri
            lines.append(json.dumps(record))

        return "\n".join(lines)
