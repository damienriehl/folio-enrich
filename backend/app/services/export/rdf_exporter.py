from __future__ import annotations

from app.models.job import Job
from app.services.export.base import ExporterBase


class RDFExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "rdf"

    @property
    def content_type(self) -> str:
        return "text/turtle"

    def export(self, job: Job) -> str:
        from rdflib import BNode, Graph, Literal, Namespace, URIRef
        from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

        g = Graph()
        FOLIO = Namespace("https://folio.openlegalstandard.org/")
        OA = Namespace("http://www.w3.org/ns/oa#")
        g.bind("folio", FOLIO)
        g.bind("oa", OA)
        g.bind("skos", SKOS)

        doc_uri = URIRef(f"urn:folio-enrich:job:{job.id}")
        g.add((doc_uri, RDF.type, OA.AnnotationCollection))

        for i, ann in enumerate(job.result.annotations):
            ann_uri = URIRef(f"urn:folio-enrich:job:{job.id}:ann:{i}")
            g.add((ann_uri, RDF.type, OA.Annotation))
            g.add((doc_uri, OA.hasAnnotation, ann_uri))

            # Target
            target = BNode()
            g.add((ann_uri, OA.hasTarget, target))
            g.add((target, OA.start, Literal(ann.span.start, datatype=XSD.integer)))
            g.add((target, OA.end, Literal(ann.span.end, datatype=XSD.integer)))
            g.add((target, OA.exact, Literal(ann.span.text)))

            # Body (concepts)
            for concept in ann.concepts:
                if concept.folio_iri:
                    concept_uri = URIRef(concept.folio_iri)
                    g.add((ann_uri, OA.hasBody, concept_uri))
                    g.add((concept_uri, RDF.type, SKOS.Concept))
                    if concept.folio_label:
                        g.add((concept_uri, SKOS.prefLabel, Literal(concept.folio_label)))

        return g.serialize(format="turtle")
