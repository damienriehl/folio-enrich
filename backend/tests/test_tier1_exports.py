import csv
import io
import json
import xml.etree.ElementTree as ET

import pytest

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.document import CanonicalText, DocumentFormat, DocumentInput, TextChunk
from app.models.job import Job, JobResult, JobStatus
from app.services.export.csv_exporter import CSVExporter
from app.services.export.json_exporter import JSONExporter
from app.services.export.jsonl_exporter import JSONLExporter
from app.services.export.jsonld_exporter import JSONLDExporter
from app.services.export.registry import list_formats
from app.services.export.xml_exporter import XMLExporter


def _make_job() -> Job:
    return Job(
        input=DocumentInput(content="The court granted the motion.", format=DocumentFormat.PLAIN_TEXT),
        status=JobStatus.COMPLETED,
        result=JobResult(
            canonical_text=CanonicalText(
                full_text="The court granted the motion.",
                chunks=[TextChunk(text="The court granted the motion.", start_offset=0, end_offset=29, chunk_index=0)],
            ),
            annotations=[
                Annotation(
                    span=Span(start=4, end=9, text="court"),
                    concepts=[
                        ConceptMatch(
                            concept_text="court",
                            folio_iri="https://folio.openlegalstandard.org/R123",
                            folio_label="Court",
                            folio_definition="A tribunal.",
                            branches=["Legal Entity"],
                            confidence=0.95,
                            source="llm",
                        )
                    ],
                ),
            ],
        ),
    )


class TestTier1Exports:
    def test_all_tier1_formats_registered(self):
        formats = list_formats()
        assert "json" in formats
        assert "jsonld" in formats
        assert "xml" in formats
        assert "csv" in formats
        assert "jsonl" in formats

    def test_json_export(self):
        job = _make_job()
        data = json.loads(JSONExporter().export(job))
        assert data["status"] == "completed"
        assert len(data["annotations"]) == 1

    def test_jsonld_export(self):
        job = _make_job()
        data = json.loads(JSONLDExporter().export(job))
        assert "@context" in data
        assert "oa" in data["@context"]
        assert "skos" in data["@context"]
        assert len(data["annotations"]) == 1
        ann = data["annotations"][0]
        assert ann["@type"] == "oa:Annotation"
        assert ann["oa:hasBody"]["@id"] == "https://folio.openlegalstandard.org/R123"

    def test_xml_export(self):
        job = _make_job()
        xml_str = XMLExporter().export(job)
        root = ET.fromstring(xml_str)
        assert root.tag == "annotations"
        assert root.get("job_id") == str(job.id)
        anns = root.find("annotations_list")
        assert len(anns) == 1

    def test_csv_export(self):
        job = _make_job()
        csv_str = CSVExporter().export(job)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        assert rows[0][0] == "span_start"  # header
        assert len(rows) == 2  # header + 1 annotation
        assert rows[1][2] == "court"  # span_text

    def test_jsonl_export(self):
        job = _make_job()
        jsonl_str = JSONLExporter().export(job)
        lines = [json.loads(line) for line in jsonl_str.strip().split("\n")]
        assert len(lines) == 1
        assert lines[0]["span_text"] == "court"
        assert len(lines[0]["concepts"]) == 1
