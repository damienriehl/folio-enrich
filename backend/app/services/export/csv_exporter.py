from __future__ import annotations

import csv
import io

from app.models.job import Job
from app.services.export.base import ExporterBase


class CSVExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "csv"

    @property
    def content_type(self) -> str:
        return "text/csv"

    def export(self, job: Job) -> str:
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "span_start", "span_end", "span_text",
            "concept_text", "folio_iri", "folio_label",
            "branch", "branch_color", "confidence", "source",
            "hierarchy_path", "definition",
        ])

        # Rows
        for ann in job.result.annotations:
            for concept in ann.concepts:
                hierarchy = " > ".join(concept.hierarchy_path) if concept.hierarchy_path else ""
                writer.writerow([
                    ann.span.start,
                    ann.span.end,
                    ann.span.text,
                    concept.concept_text,
                    concept.folio_iri or "",
                    concept.folio_label or "",
                    concept.branch or "",
                    concept.branch_color or "",
                    f"{concept.confidence:.4f}",
                    concept.source,
                    hierarchy,
                    concept.folio_definition or "",
                ])

        return output.getvalue()
