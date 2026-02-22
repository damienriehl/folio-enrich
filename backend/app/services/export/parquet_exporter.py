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
                    "branch": concept.branch or "",
                    "confidence": concept.confidence,
                    "source": concept.source,
                    "document_type": job.result.metadata.get("document_type", ""),
                })

        if not rows:
            rows = [{"job_id": str(job.id), "span_start": 0, "span_end": 0,
                     "span_text": "", "concept_text": "", "folio_iri": "",
                     "folio_label": "", "branch": "", "confidence": 0.0,
                     "source": "", "document_type": ""}]

        table = pa.Table.from_pylist(rows)
        buf = io.BytesIO()
        pq.write_table(table, buf)
        return buf.getvalue()
