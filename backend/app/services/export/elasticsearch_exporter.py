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

        return "\n".join(lines) + "\n" if lines else ""
