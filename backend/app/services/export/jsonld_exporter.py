from __future__ import annotations

import json

from app.models.job import Job
from app.services.export.base import ExporterBase


class JSONLDExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "jsonld"

    @property
    def content_type(self) -> str:
        return "application/ld+json"

    def export(self, job: Job) -> str:
        annotations_ld = []
        for ann in job.result.annotations:
            for concept in ann.concepts:
                annotations_ld.append({
                    "@type": "oa:Annotation",
                    "oa:hasTarget": {
                        "@type": "oa:SpecificResource",
                        "oa:hasSelector": {
                            "@type": "oa:TextPositionSelector",
                            "oa:start": ann.span.start,
                            "oa:end": ann.span.end,
                            "oa:exact": ann.span.text,
                        },
                    },
                    "oa:hasBody": {
                        k: v
                        for k, v in {
                            "@type": "skos:Concept",
                            "@id": concept.folio_iri or "",
                            "skos:prefLabel": concept.folio_label or concept.concept_text,
                            "skos:definition": concept.folio_definition or "",
                            "folio:branch": concept.branches[0] if concept.branches else "",
                            "skos:altLabel": concept.folio_alt_labels or None,
                            "skos:example": concept.folio_examples or None,
                            "rdfs:seeAlso": concept.folio_see_also or None,
                            "dc:source": concept.folio_source or None,
                        }.items()
                        if v is not None
                    },
                    "oa:motivatedBy": "oa:tagging",
                    "schema:confidence": concept.confidence,
                })

        output = {
            "@context": {
                "oa": "http://www.w3.org/ns/oa#",
                "skos": "http://www.w3.org/2004/02/skos/core#",
                "schema": "http://schema.org/",
                "folio": "https://folio.openlegalstandard.org/",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "dc": "http://purl.org/dc/elements/1.1/",
            },
            "@type": "oa:AnnotationCollection",
            "schema:name": f"FOLIO Enrich annotations for job {job.id}",
            "oa:annotatedAt": job.created_at.isoformat(),
            "annotations": annotations_ld,
        }
        return json.dumps(output, indent=2)
