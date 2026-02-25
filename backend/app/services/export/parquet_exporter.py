from __future__ import annotations

import io

from app.models.job import Job
from app.services.export.base import ExporterBase


class ParquetExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "parquet"

    @property
    def content_type(self) -> str:
        return "application/octet-stream"

    def export(self, job: Job) -> bytes:
        import pyarrow as pa
        import pyarrow.parquet as pq

        rows = []
        for ann in job.result.annotations:
            for concept in ann.concepts:
                rows.append({
                    "job_id": str(job.id),
                    "span_start": ann.span.start,
                    "span_end": ann.span.end,
                    "span_text": ann.span.text,
                    "concept_text": concept.concept_text,
                    "folio_iri": concept.folio_iri or "",
                    "folio_label": concept.folio_label or "",
                    "branch": concept.branches[0] if concept.branches else "",
                    "confidence": concept.confidence,
                    "source": concept.source,
                    "document_type": job.result.metadata.get("document_type", ""),
                })

        if not rows:
            rows = [{"job_id": str(job.id), "span_start": 0, "span_end": 0,
                     "span_text": "", "concept_text": "", "folio_iri": "",
                     "folio_label": "", "branch": "", "confidence": 0.0,  # noqa: E501
                     "source": "", "document_type": ""}]

        table = pa.Table.from_pylist(rows)

        # Individuals table
        ind_rows = []
        for ind in job.result.individuals:
            class_labels = "; ".join(cl.folio_label or "" for cl in ind.class_links)
            class_iris = "; ".join(cl.folio_iri or "" for cl in ind.class_links)
            ind_rows.append({
                "job_id": str(job.id),
                "individual_id": ind.id,
                "name": ind.name,
                "mention_text": ind.mention_text,
                "individual_type": ind.individual_type,
                "span_start": ind.span.start,
                "span_end": ind.span.end,
                "class_labels": class_labels,
                "class_iris": class_iris,
                "confidence": ind.confidence,
                "source": ind.source,
                "normalized_form": ind.normalized_form or "",
                "url": ind.url or "",
            })

        # Properties table
        prop_rows = []
        for prop in job.result.properties:
            prop_rows.append({
                "job_id": str(job.id),
                "property_id": prop.id,
                "property_text": prop.property_text,
                "folio_iri": prop.folio_iri or "",
                "folio_label": prop.folio_label or "",
                "span_start": prop.span.start,
                "span_end": prop.span.end,
                "confidence": prop.confidence,
                "source": prop.source,
                "match_type": prop.match_type or "",
                "domain_iris": "; ".join(prop.domain_iris),
                "range_iris": "; ".join(prop.range_iris),
            })

        buf = io.BytesIO()
        pq.write_table(table, buf, row_group_size=len(rows) or 1)

        if ind_rows:
            ind_table = pa.Table.from_pylist(ind_rows)
            pq.write_table(ind_table, buf)

        if prop_rows:
            prop_table = pa.Table.from_pylist(prop_rows)
            pq.write_table(prop_table, buf)

        return buf.getvalue()
