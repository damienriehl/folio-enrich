import base64
import io
from unittest.mock import patch

import pytest

from app.models.document import DocumentFormat, DocumentInput
from app.services.ingestion.pdf_ingestor import PDFIngestor
from app.services.ingestion.plain_text import PlainTextIngestor
from app.services.ingestion.registry import detect_format, ingest


class TestPlainTextIngestor:
    def test_ingest_returns_content(self):
        doc = DocumentInput(content="Hello world")
        ingestor = PlainTextIngestor()
        assert ingestor.ingest(doc) == "Hello world"

    def test_ingest_preserves_whitespace(self):
        doc = DocumentInput(content="Line 1\n\nLine 2")
        ingestor = PlainTextIngestor()
        assert ingestor.ingest(doc) == "Line 1\n\nLine 2"


class TestFormatDetection:
    def test_detect_txt_extension(self):
        assert detect_format("doc.txt", "") == DocumentFormat.PLAIN_TEXT

    def test_detect_md_extension(self):
        assert detect_format("readme.md", "") == DocumentFormat.MARKDOWN

    def test_detect_html_extension(self):
        assert detect_format("page.html", "") == DocumentFormat.HTML

    def test_detect_htm_extension(self):
        assert detect_format("page.htm", "") == DocumentFormat.HTML

    def test_detect_pdf_extension(self):
        assert detect_format("file.pdf", "") == DocumentFormat.PDF

    def test_detect_docx_extension(self):
        assert detect_format("file.docx", "") == DocumentFormat.WORD

    def test_detect_html_content(self):
        assert detect_format(None, "<html><body>Hi</body></html>") == DocumentFormat.HTML

    def test_detect_markdown_content(self):
        assert detect_format(None, "# Heading\n\nSome text") == DocumentFormat.MARKDOWN

    def test_detect_plain_text_fallback(self):
        assert detect_format(None, "Just plain text.") == DocumentFormat.PLAIN_TEXT


class TestIngestRegistry:
    def test_ingest_plain_text(self):
        doc = DocumentInput(content="test content", format=DocumentFormat.PLAIN_TEXT)
        assert ingest(doc) == "test content"

    def test_ingest_invalid_pdf_raises(self):
        doc = DocumentInput(content="test", format=DocumentFormat.PDF)
        with pytest.raises(Exception):
            ingest(doc)


# Minimal valid 1-page PDF with "Hello World" text
_MINI_PDF_B64 = (
    "JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5k"
    "b2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4K"
    "ZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3gg"
    "WzAgMCA2MTIgNzkyXSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAv"
    "RjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA0NCA+PgpzdHJl"
    "YW0KQlQgL0YxIDEyIFRmIDEwMCA3MDAgVGQgKEhlbGxvIFdvcmxkKSBUaiBFVAplbmRzdHJl"
    "YW0KZW5kb2JqCjUgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNl"
    "Rm9udCAvSGVsdmV0aWNhID4+CmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYg"
    "CjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAowMDAwMDAwMTE1MDAwMD"
    "AgbiAKMDAwMDAwMDI2NiAwMDAwMCBuIAowMDAwMDAwMzYwIDAwMDAwIG4gCnRyYWlsZXIKPDwg"
    "L1NpemUgNiAvUm9vdCAxIDAgUiA+PgpzdGFydHhyZWYKNDQxCiUlRU9G"
)


class TestPDFIngestorPymupdf:
    """Test the default PyMuPDF backend."""

    def test_ingest_extracts_text(self):
        doc = DocumentInput(content=_MINI_PDF_B64, filename="test.pdf")
        ingestor = PDFIngestor()
        text = ingestor.ingest(doc)
        assert "Hello World" in text

    def test_ingest_with_elements_returns_elements(self):
        doc = DocumentInput(content=_MINI_PDF_B64, filename="test.pdf")
        ingestor = PDFIngestor()
        text, elements = ingestor.ingest_with_elements(doc)
        assert "Hello World" in text
        assert len(elements) >= 1
        assert elements[0].page == 1


class TestPDFIngestorPypdf:
    """Test the pypdf fallback backend by patching _PDF_BACKEND."""

    def test_ingest_extracts_text(self):
        doc = DocumentInput(content=_MINI_PDF_B64, filename="test.pdf")
        ingestor = PDFIngestor()
        with patch("app.services.ingestion.pdf_ingestor._PDF_BACKEND", "pypdf"):
            text = ingestor.ingest(doc)
        assert "Hello World" in text

    def test_ingest_with_elements_returns_elements(self):
        doc = DocumentInput(content=_MINI_PDF_B64, filename="test.pdf")
        ingestor = PDFIngestor()
        with patch("app.services.ingestion.pdf_ingestor._PDF_BACKEND", "pypdf"):
            text, elements = ingestor.ingest_with_elements(doc)
        assert "Hello World" in text
        assert len(elements) >= 1
        assert elements[0].page == 1

    def test_fallback_used_when_pymupdf_missing(self):
        """Verify _PDF_BACKEND can be set to 'pypdf'."""
        with patch("app.services.ingestion.pdf_ingestor._PDF_BACKEND", "pypdf"):
            from app.services.ingestion import pdf_ingestor

            assert pdf_ingestor._PDF_BACKEND == "pypdf"
