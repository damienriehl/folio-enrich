import json

import pytest

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.document import CanonicalText, DocumentFormat, DocumentInput, TextChunk
from app.models.job import Job, JobResult, JobStatus
from app.services.export.json_exporter import JSONExporter
from app.services.export.registry import get_exporter, list_formats


def _make_test_job() -> Job:
    job = Job(
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
                            folio_definition="A tribunal for the administration of justice.",
                            branches=["Legal Entity"],
                            confidence=0.95,
                            source="llm",
                        )
                    ],
                ),
                Annotation(
                    span=Span(start=22, end=28, text="motion"),
                    concepts=[
                        ConceptMatch(
                            concept_text="motion",
                            folio_iri="https://folio.openlegalstandard.org/R456",
                            folio_label="Motion",
                            branches=["Event"],
                            confidence=0.88,
                            source="llm",
                        )
                    ],
                ),
            ],
        ),
    )
    return job


class TestJSONExporter:
    def test_export_produces_valid_json(self):
        exporter = JSONExporter()
        job = _make_test_job()
        result = exporter.export(job)
        data = json.loads(result)
        assert data["job_id"] == str(job.id)
        assert data["status"] == "completed"
        assert len(data["annotations"]) == 2

    def test_export_annotations_structure(self):
        exporter = JSONExporter()
        job = _make_test_job()
        data = json.loads(exporter.export(job))
        ann = data["annotations"][0]
        assert "span" in ann
        assert ann["span"]["text"] == "court"
        assert ann["span"]["start"] == 4
        assert ann["span"]["end"] == 9
        assert len(ann["concepts"]) == 1
        assert ann["concepts"][0]["folio_iri"] == "https://folio.openlegalstandard.org/R123"

    def test_export_statistics(self):
        exporter = JSONExporter()
        job = _make_test_job()
        data = json.loads(exporter.export(job))
        assert data["statistics"]["total_annotations"] == 2
        assert data["statistics"]["unique_concepts"] == 2

    def test_export_no_internal_metadata(self):
        exporter = JSONExporter()
        job = _make_test_job()
        job.result.metadata["_raw_text"] = "should not appear"
        job.result.metadata["public_key"] = "should appear"
        data = json.loads(exporter.export(job))
        assert "_raw_text" not in data["metadata"]
        assert data["metadata"]["public_key"] == "should appear"


class TestExportRegistry:
    def test_json_registered(self):
        assert "json" in list_formats()

    def test_get_json_exporter(self):
        exporter = get_exporter("json")
        assert isinstance(exporter, JSONExporter)

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown export format"):
            get_exporter("nonexistent_format_xyz")
