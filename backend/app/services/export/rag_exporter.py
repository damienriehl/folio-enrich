from __future__ import annotations

import json

from app.models.job import Job
from app.services.export.base import ExporterBase


class RAGExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "rag"

    @property
    def content_type(self) -> str:
        return "application/json"

    def export(self, job: Job) -> str:
        if job.result.canonical_text is None:
            return json.dumps([])

        chunks = []
        for chunk in job.result.canonical_text.chunks:
            # Find annotations within this chunk
            chunk_annotations = []
            for ann in job.result.annotations:
                if ann.span.start >= chunk.start_offset and ann.span.end <= chunk.end_offset:
                    chunk_annotations.append({
                        "span_text": ann.span.text,
                        "concepts": [
                            {
                                "folio_iri": c.folio_iri,
                                "folio_label": c.folio_label,
                                "branch": c.branches[0] if c.branches else "",
                                "branches": c.branches,
                                "confidence": c.confidence,
                            }
                            for c in ann.concepts
                        ],
                    })

            chunks.append({
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "start_offset": chunk.start_offset,
                "end_offset": chunk.end_offset,
                "concepts": list({
                    c.folio_iri or c.concept_text
                    for a in chunk_annotations
                    for c in [type("C", (), ca)() for ca in a["concepts"]]  # noqa - skip
                }) if False else [  # simpler approach
                    c["folio_iri"] or c.get("folio_label", "")
                    for a in chunk_annotations
                    for c in a["concepts"]
                ],
                "annotations": chunk_annotations,
                "metadata": {
                    "document_type": job.result.metadata.get("document_type", ""),
                    "job_id": str(job.id),
                },
            })

        return json.dumps(chunks, indent=2)
