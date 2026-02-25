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
                    concept.branches[0] if concept.branches else "",
                    concept.branch_color or "",
                    f"{concept.confidence:.4f}",
                    concept.source,
                    hierarchy,
                    concept.folio_definition or "",
                ])

        # Individuals section (blank row separator)
        if job.result.individuals:
            writer.writerow([])
            writer.writerow([
                "span_start", "span_end", "mention_text",
                "name", "individual_type", "class_labels",
                "confidence", "source", "normalized_form", "url",
            ])
            for ind in job.result.individuals:
                class_labels = "; ".join(
                    cl.folio_label or "" for cl in ind.class_links
                )
                writer.writerow([
                    ind.span.start,
                    ind.span.end,
                    ind.mention_text,
                    ind.name,
                    ind.individual_type,
                    class_labels,
                    f"{ind.confidence:.4f}",
                    ind.source,
                    ind.normalized_form or "",
                    ind.url or "",
                ])

        # Properties section (blank row separator)
        if job.result.properties:
            writer.writerow([])
            writer.writerow([
                "span_start", "span_end", "property_text",
                "folio_iri", "folio_label", "confidence",
                "source", "match_type", "domain_iris", "range_iris",
            ])
            for prop in job.result.properties:
                writer.writerow([
                    prop.span.start,
                    prop.span.end,
                    prop.property_text,
                    prop.folio_iri or "",
                    prop.folio_label or "",
                    f"{prop.confidence:.4f}",
                    prop.source,
                    prop.match_type or "",
                    "; ".join(prop.domain_iris),
                    "; ".join(prop.range_iris),
                ])

        return output.getvalue()
