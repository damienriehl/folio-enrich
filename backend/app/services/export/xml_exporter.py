from __future__ import annotations

import xml.etree.ElementTree as ET

from app.models.job import Job
from app.services.export.base import ExporterBase


class XMLExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "xml"

    @property
    def content_type(self) -> str:
        return "application/xml"

    def export(self, job: Job) -> str:
        root = ET.Element("annotations")
        root.set("job_id", str(job.id))
        root.set("status", job.status.value)

        doc_elem = ET.SubElement(root, "document")
        if job.input:
            ET.SubElement(doc_elem, "format").text = job.input.format.value
            if job.input.filename:
                ET.SubElement(doc_elem, "filename").text = job.input.filename

        meta_elem = ET.SubElement(root, "metadata")
        for k, v in (job.result.metadata or {}).items():
            if not k.startswith("_"):
                field = ET.SubElement(meta_elem, "field")
                field.set("name", k)
                field.text = str(v)

        anns_elem = ET.SubElement(root, "annotations_list")
        for ann in job.result.annotations:
            ann_elem = ET.SubElement(anns_elem, "annotation")
            span_elem = ET.SubElement(ann_elem, "span")
            span_elem.set("start", str(ann.span.start))
            span_elem.set("end", str(ann.span.end))
            span_elem.text = ann.span.text

            for concept in ann.concepts:
                c_elem = ET.SubElement(ann_elem, "concept")
                ET.SubElement(c_elem, "text").text = concept.concept_text
                if concept.folio_iri:
                    ET.SubElement(c_elem, "iri").text = concept.folio_iri
                if concept.folio_label:
                    ET.SubElement(c_elem, "label").text = concept.folio_label
                if concept.branches:
                    ET.SubElement(c_elem, "branch").text = concept.branches[0]
                ET.SubElement(c_elem, "confidence").text = str(concept.confidence)
                ET.SubElement(c_elem, "source").text = concept.source

        # Individuals
        inds_elem = ET.SubElement(root, "individuals")
        for ind in job.result.individuals:
            ind_elem = ET.SubElement(inds_elem, "individual")
            ind_elem.set("id", ind.id)
            ind_elem.set("type", ind.individual_type)
            ET.SubElement(ind_elem, "name").text = ind.name
            ET.SubElement(ind_elem, "mention_text").text = ind.mention_text
            span_elem = ET.SubElement(ind_elem, "span")
            span_elem.set("start", str(ind.span.start))
            span_elem.set("end", str(ind.span.end))
            span_elem.text = ind.span.text
            ET.SubElement(ind_elem, "confidence").text = str(ind.confidence)
            ET.SubElement(ind_elem, "source").text = ind.source
            if ind.normalized_form:
                ET.SubElement(ind_elem, "normalized_form").text = ind.normalized_form
            if ind.url:
                ET.SubElement(ind_elem, "url").text = ind.url
            for cl in ind.class_links:
                cl_elem = ET.SubElement(ind_elem, "class_link")
                if cl.folio_iri:
                    ET.SubElement(cl_elem, "iri").text = cl.folio_iri
                if cl.folio_label:
                    ET.SubElement(cl_elem, "label").text = cl.folio_label
                ET.SubElement(cl_elem, "confidence").text = str(cl.confidence)

        # Properties
        props_elem = ET.SubElement(root, "properties")
        for prop in job.result.properties:
            prop_elem = ET.SubElement(props_elem, "property")
            prop_elem.set("id", prop.id)
            ET.SubElement(prop_elem, "property_text").text = prop.property_text
            if prop.folio_iri:
                ET.SubElement(prop_elem, "iri").text = prop.folio_iri
            if prop.folio_label:
                ET.SubElement(prop_elem, "label").text = prop.folio_label
            span_elem = ET.SubElement(prop_elem, "span")
            span_elem.set("start", str(prop.span.start))
            span_elem.set("end", str(prop.span.end))
            span_elem.text = prop.span.text
            ET.SubElement(prop_elem, "confidence").text = str(prop.confidence)
            ET.SubElement(prop_elem, "source").text = prop.source
            if prop.domain_iris:
                for d in prop.domain_iris:
                    ET.SubElement(prop_elem, "domain").text = d
            if prop.range_iris:
                for r in prop.range_iris:
                    ET.SubElement(prop_elem, "range").text = r
            if prop.inverse_of_iri:
                ET.SubElement(prop_elem, "inverse_of").text = prop.inverse_of_iri

        ET.indent(root)
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
