from __future__ import annotations

from app.models.job import Job
from app.services.export.base import ExporterBase


class BratExporter(ExporterBase):
    """Export in brat standoff annotation format."""

    @property
    def format_name(self) -> str:
        return "brat"

    @property
    def content_type(self) -> str:
        return "text/plain"

    def export(self, job: Job) -> str:
        lines = []
        t_idx = 1
        a_idx = 1

        for ann in job.result.annotations:
            label = "FOLIO_CONCEPT"
            if ann.concepts and ann.concepts[0].branches:
                label = ann.concepts[0].branches[0].replace(" ", "_")

            # T line: entity annotation
            lines.append(f"T{t_idx}\t{label} {ann.span.start} {ann.span.end}\t{ann.span.text}")

            # A lines: attributes
            for concept in ann.concepts:
                if concept.folio_iri:
                    lines.append(f"A{a_idx}\tFOLIO_IRI T{t_idx} {concept.folio_iri}")
                    a_idx += 1
                if concept.folio_label:
                    lines.append(f"A{a_idx}\tFOLIO_Label T{t_idx} {concept.folio_label}")
                    a_idx += 1

            t_idx += 1

        # Individual annotations
        for ind in job.result.individuals:
            label = ind.individual_type.upper().replace(" ", "_")
            if ind.class_links and ind.class_links[0].folio_label:
                label = ind.class_links[0].folio_label.replace(" ", "_")

            lines.append(f"T{t_idx}\t{label} {ind.span.start} {ind.span.end}\t{ind.mention_text}")

            if ind.name != ind.mention_text:
                lines.append(f"A{a_idx}\tCanonicalName T{t_idx} {ind.name}")
                a_idx += 1

            for cl in ind.class_links:
                if cl.folio_iri:
                    lines.append(f"A{a_idx}\tFOLIO_IRI T{t_idx} {cl.folio_iri}")
                    a_idx += 1

            t_idx += 1

        # Property annotations
        for prop in job.result.properties:
            label = (prop.folio_label or "PROPERTY").replace(" ", "_")
            lines.append(f"T{t_idx}\t{label} {prop.span.start} {prop.span.end}\t{prop.property_text}")

            if prop.folio_iri:
                lines.append(f"A{a_idx}\tFOLIO_IRI T{t_idx} {prop.folio_iri}")
                a_idx += 1

            t_idx += 1

        return "\n".join(lines)
