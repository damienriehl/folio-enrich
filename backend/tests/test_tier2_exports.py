import json

import pytest

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.document import CanonicalText, DocumentFormat, DocumentInput, TextChunk
from app.models.job import Job, JobResult, JobStatus
from app.services.export.brat_exporter import BratExporter
from app.services.export.elasticsearch_exporter import ElasticsearchExporter
from app.services.export.html_exporter import HTMLExporter
from app.services.export.neo4j_exporter import Neo4jExporter
from app.services.export.parquet_exporter import ParquetExporter
from app.services.export.rag_exporter import RAGExporter
from app.services.export.rdf_exporter import RDFExporter
from app.services.export.registry import list_formats


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


class TestTier2Exports:
    def test_all_13_formats_registered(self):
        formats = list_formats()
        assert len(formats) == 13
        expected = {"json", "jsonld", "xml", "csv", "jsonl", "parquet", "elasticsearch", "neo4j", "rag", "rdf", "brat", "html", "excel"}
        assert set(formats) == expected

    def test_parquet_export(self):
        job = _make_job()
        result = ParquetExporter().export(job)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_elasticsearch_export(self):
        job = _make_job()
        result = ElasticsearchExporter().export(job)
        lines = result.strip().split("\n")
        assert len(lines) == 2  # action + doc
        action = json.loads(lines[0])
        assert "index" in action

    def test_neo4j_export(self):
        job = _make_job()
        result = Neo4jExporter().export(job)
        assert "# NODES" in result
        assert "# RELATIONSHIPS" in result
        assert "CONTAINS_CONCEPT" in result

    def test_rag_export(self):
        job = _make_job()
        result = json.loads(RAGExporter().export(job))
        assert isinstance(result, list)
        assert len(result) == 1  # 1 chunk
        assert "text" in result[0]
        assert "annotations" in result[0]

    def test_rdf_export(self):
        job = _make_job()
        result = RDFExporter().export(job)
        assert "folio:" in result or "oa:" in result
        assert "skos:Concept" in result

    def test_brat_export(self):
        job = _make_job()
        result = BratExporter().export(job)
        assert result.startswith("T1\t")
        assert "4 9" in result  # offsets
        assert "court" in result

    def test_html_export(self):
        job = _make_job()
        result = HTMLExporter().export(job)
        assert "<html>" in result
        assert "folio-annotation" in result
        assert "court" in result

    def test_excel_export(self):
        from app.services.export.excel_exporter import ExcelExporter
        job = _make_job()
        result = ExcelExporter().export(job)
        assert isinstance(result, bytes)
        assert len(result) > 0
        # Verify it's a valid xlsx by checking magic bytes (PK zip)
        assert result[:2] == b"PK"

    def test_excel_export_has_data(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from app.services.export.excel_exporter import ExcelExporter
        job = _make_job()
        result = ExcelExporter().export(job)
        wb = load_workbook(BytesIO(result))
        ws = wb.active
        assert ws.title == "FOLIO Annotations"
        # Header row + 1 data row
        rows = list(ws.rows)
        assert len(rows) == 2
        # Check header
        assert rows[0][0].value == "Span Start"
        # Check data
        assert rows[1][2].value == "court"  # span text
        assert rows[1][3].value == "court"  # concept text
