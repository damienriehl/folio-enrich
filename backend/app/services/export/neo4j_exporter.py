from __future__ import annotations

import csv
import io

from app.models.job import Job
from app.services.export.base import ExporterBase


class Neo4jExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "neo4j"

    @property
    def content_type(self) -> str:
        return "text/csv"

    def export(self, job: Job) -> str:
        # Produce two CSVs: nodes and relationships, separated by a marker
        nodes_buf = io.StringIO()
        rels_buf = io.StringIO()

        nodes_writer = csv.writer(nodes_buf)
        rels_writer = csv.writer(rels_buf)

        # Nodes header
        nodes_writer.writerow([":ID", "name", "iri", "branch", ":LABEL"])

        seen_concepts: set[str] = set()
        concept_id = 0

        # Document node
        doc_id = f"doc_{job.id}"
        nodes_writer.writerow([doc_id, str(job.id), "", "", "Document"])

        # Relationships header
        rels_writer.writerow([":START_ID", ":END_ID", ":TYPE", "confidence", "span_start", "span_end"])

        for ann in job.result.annotations:
            for concept in ann.concepts:
                iri = concept.folio_iri or concept.concept_text
                if iri not in seen_concepts:
                    seen_concepts.add(iri)
                    nodes_writer.writerow([
                        iri,
                        concept.folio_label or concept.concept_text,
                        concept.folio_iri or "",
                        concept.branches[0] if concept.branches else "",
                        "Concept",
                    ])
                # Relationship
                rels_writer.writerow([
                    doc_id, iri, "CONTAINS_CONCEPT",
                    f"{concept.confidence:.4f}",
                    ann.span.start, ann.span.end,
                ])

        return (
            "# NODES\n" + nodes_buf.getvalue() +
            "\n# RELATIONSHIPS\n" + rels_buf.getvalue()
        )
