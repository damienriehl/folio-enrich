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
                        "branch": c.branch,
                        "confidence": c.confidence,
                        "source": c.source,
                    }
                    for c in ann.concepts
                ],
            }
            lines.append(json.dumps(record))
        return "\n".join(lines)
