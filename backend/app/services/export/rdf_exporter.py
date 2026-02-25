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

        # OWL Named Individuals
        for i, ind in enumerate(job.result.individuals):
            ind_uri = URIRef(f"urn:folio-enrich:job:{job.id}:ind:{i}")
            g.add((ind_uri, RDF.type, OWL.NamedIndividual))
            g.add((doc_uri, FOLIO.hasIndividual, ind_uri))
            g.add((ind_uri, RDFS.label, Literal(ind.name)))

            # Target span
            ind_target = BNode()
            g.add((ind_uri, OA.hasTarget, ind_target))
            g.add((ind_target, OA.start, Literal(ind.span.start, datatype=XSD.integer)))
            g.add((ind_target, OA.end, Literal(ind.span.end, datatype=XSD.integer)))
            g.add((ind_target, OA.exact, Literal(ind.mention_text)))

            # Class links (rdf:type)
            for cl in ind.class_links:
                if cl.folio_iri:
                    g.add((ind_uri, RDF.type, URIRef(cl.folio_iri)))

        # OWL ObjectProperties
        for i, prop in enumerate(job.result.properties):
            prop_uri = URIRef(prop.folio_iri) if prop.folio_iri else URIRef(f"urn:folio-enrich:job:{job.id}:prop:{i}")
            g.add((prop_uri, RDF.type, OWL.ObjectProperty))
            g.add((doc_uri, FOLIO.hasProperty, prop_uri))
            if prop.folio_label:
                g.add((prop_uri, RDFS.label, Literal(prop.folio_label)))

            # Target span
            prop_target = BNode()
            g.add((prop_uri, OA.hasTarget, prop_target))
            g.add((prop_target, OA.start, Literal(prop.span.start, datatype=XSD.integer)))
            g.add((prop_target, OA.end, Literal(prop.span.end, datatype=XSD.integer)))
            g.add((prop_target, OA.exact, Literal(prop.property_text)))

            # Domain and range
            for d_iri in prop.domain_iris:
                g.add((prop_uri, RDFS.domain, URIRef(d_iri)))
            for r_iri in prop.range_iris:
                g.add((prop_uri, RDFS.range, URIRef(r_iri)))
            if prop.inverse_of_iri:
                g.add((prop_uri, OWL.inverseOf, URIRef(prop.inverse_of_iri)))

        return g.serialize(format="turtle")
