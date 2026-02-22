"""Tests for RTF ingestion."""

import pytest

from app.models.document import DocumentFormat, DocumentInput


class TestRTFIngestion:
    def test_rtf_format_enum(self):
        assert DocumentFormat.RTF == "rtf"

    def test_rtf_ingestor_simple(self):
        from app.services.ingestion.rtf_ingestor import RTFIngestor

        rtf_content = r"{\rtf1\ansi Hello World.}"
        doc = DocumentInput(content=rtf_content, format=DocumentFormat.RTF)
        ingestor = RTFIngestor()
        text = ingestor.ingest(doc)
        assert "Hello World" in text

    def test_rtf_registered_in_registry(self):
        from app.services.ingestion.registry import get_ingestor

        ingestor = get_ingestor(DocumentFormat.RTF)
        assert ingestor is not None

    def test_detect_format_rtf(self):
        from app.services.ingestion.registry import detect_format

        fmt = detect_format("document.rtf", "")
        assert fmt == DocumentFormat.RTF
