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
                if concept.branch:
                    ET.SubElement(c_elem, "branch").text = concept.branch
                ET.SubElement(c_elem, "confidence").text = str(concept.confidence)
                ET.SubElement(c_elem, "source").text = concept.source

        ET.indent(root)
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
