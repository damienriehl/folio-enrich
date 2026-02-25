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

        # Individual nodes and relationships
        for ind in job.result.individuals:
            ind_id = f"ind_{ind.id[:8]}"
            nodes_writer.writerow([
                ind_id,
                ind.name,
                "",
                "",
                "Individual",
            ])
            # Link individual to document
            rels_writer.writerow([
                doc_id, ind_id, "CONTAINS_INDIVIDUAL",
                f"{ind.confidence:.4f}",
                ind.span.start, ind.span.end,
            ])
            # Link individual to its class concepts
            for cl in ind.class_links:
                concept_iri = cl.folio_iri
                if concept_iri and concept_iri in seen_concepts:
                    rels_writer.writerow([
                        ind_id, concept_iri, "INSTANCE_OF",
                        f"{cl.confidence:.4f}",
                        "", "",
                    ])

        # Property nodes and relationships
        for prop in job.result.properties:
            prop_id = f"prop_{prop.id[:8]}"
            nodes_writer.writerow([
                prop_id,
                prop.folio_label or prop.property_text,
                prop.folio_iri or "",
                "",
                "Property",
            ])
            # Link property to document
            rels_writer.writerow([
                doc_id, prop_id, "CONTAINS_PROPERTY",
                f"{prop.confidence:.4f}",
                prop.span.start, prop.span.end,
            ])
            # Link property to domain/range concepts
            for domain_iri in prop.domain_iris:
                if domain_iri in seen_concepts:
                    rels_writer.writerow([
                        prop_id, domain_iri, "HAS_DOMAIN",
                        "", "", "",
                    ])
            for range_iri in prop.range_iris:
                if range_iri in seen_concepts:
                    rels_writer.writerow([
                        prop_id, range_iri, "HAS_RANGE",
                        "", "", "",
                    ])

        return (
            "# NODES\n" + nodes_buf.getvalue() +
            "\n# RELATIONSHIPS\n" + rels_buf.getvalue()
        )
