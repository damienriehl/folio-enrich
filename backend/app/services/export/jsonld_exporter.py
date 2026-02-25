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

        # OWL Named Individuals
        individuals_ld = []
        for ind in job.result.individuals:
            ind_obj = {
                "@type": "owl:NamedIndividual",
                "schema:name": ind.name,
                "oa:hasTarget": {
                    "@type": "oa:SpecificResource",
                    "oa:hasSelector": {
                        "@type": "oa:TextPositionSelector",
                        "oa:start": ind.span.start,
                        "oa:end": ind.span.end,
                        "oa:exact": ind.mention_text,
                    },
                },
                "folio:individualType": ind.individual_type,
                "schema:confidence": ind.confidence,
                "folio:source": ind.source,
                "rdf:type": [
                    {
                        k: v
                        for k, v in {
                            "@id": cl.folio_iri or "",
                            "skos:prefLabel": cl.folio_label or "",
                            "folio:branch": cl.branch,
                        }.items()
                        if v
                    }
                    for cl in ind.class_links
                ],
            }
            if ind.normalized_form:
                ind_obj["folio:normalizedForm"] = ind.normalized_form
            if ind.url:
                ind_obj["schema:url"] = ind.url
            individuals_ld.append(ind_obj)

        # OWL ObjectProperties
        properties_ld = []
        for prop in job.result.properties:
            prop_obj = {
                "@type": "owl:ObjectProperty",
                "oa:hasTarget": {
                    "@type": "oa:SpecificResource",
                    "oa:hasSelector": {
                        "@type": "oa:TextPositionSelector",
                        "oa:start": prop.span.start,
                        "oa:end": prop.span.end,
                        "oa:exact": prop.property_text,
                    },
                },
                "schema:confidence": prop.confidence,
                "folio:source": prop.source,
            }
            if prop.folio_iri:
                prop_obj["@id"] = prop.folio_iri
            if prop.folio_label:
                prop_obj["skos:prefLabel"] = prop.folio_label
            if prop.folio_definition:
                prop_obj["skos:definition"] = prop.folio_definition
            if prop.domain_iris:
                prop_obj["rdfs:domain"] = prop.domain_iris
            if prop.range_iris:
                prop_obj["rdfs:range"] = prop.range_iris
            if prop.inverse_of_iri:
                prop_obj["owl:inverseOf"] = {"@id": prop.inverse_of_iri}
            properties_ld.append(prop_obj)

        output = {
            "@context": {
                "oa": "http://www.w3.org/ns/oa#",
                "owl": "http://www.w3.org/2002/07/owl#",
                "skos": "http://www.w3.org/2004/02/skos/core#",
                "schema": "http://schema.org/",
                "folio": "https://folio.openlegalstandard.org/",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                "dc": "http://purl.org/dc/elements/1.1/",
            },
            "@type": "oa:AnnotationCollection",
            "schema:name": f"FOLIO Enrich annotations for job {job.id}",
            "oa:annotatedAt": job.created_at.isoformat(),
            "annotations": annotations_ld,
            "individuals": individuals_ld,
            "properties": properties_ld,
        }
        return json.dumps(output, indent=2)
