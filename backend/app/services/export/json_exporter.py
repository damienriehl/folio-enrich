from __future__ import annotations

import json

from app.models.job import Job
from app.services.export.base import ExporterBase


class JSONExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "json"

    @property
    def content_type(self) -> str:
        return "application/json"

    def export(self, job: Job) -> str:
        output = {
            "job_id": str(job.id),
            "status": job.status.value,
            "document": {
                "format": job.input.format.value if job.input else None,
                "filename": job.input.filename if job.input else None,
            },
            "metadata": {
                k: v
                for k, v in (job.result.metadata or {}).items()
                if not k.startswith("_")
            },
            "annotations": [
                {
                    "span": {
                        "start": a.span.start,
                        "end": a.span.end,
                        "text": a.span.text,
                    },
                    "concepts": [
                        {
                            k: v
                            for k, v in {
                                "concept_text": c.concept_text,
                                "folio_iri": c.folio_iri,
                                "folio_label": c.folio_label,
                                "folio_definition": c.folio_definition,
                                "branch": c.branches[0] if c.branches else "",
                                "branches": c.branches,
                                "confidence": c.confidence,
                                "source": c.source,
                                "folio_examples": c.folio_examples or None,
                                "folio_alt_labels": c.folio_alt_labels or None,
                                "folio_see_also": c.folio_see_also or None,
                                "folio_source": c.folio_source or None,
                            }.items()
                            if v is not None
                        }
                        for c in a.concepts
                    ],
                }
                for a in job.result.annotations
            ],
            "statistics": {
                "total_annotations": len(job.result.annotations),
                "unique_concepts": len(
                    {
                        c.folio_iri
                        for a in job.result.annotations
                        for c in a.concepts
                        if c.folio_iri
                    }
                ),
            },
        }
        return json.dumps(output, indent=2)
