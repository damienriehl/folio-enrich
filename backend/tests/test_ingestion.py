import pytest

from app.models.document import DocumentFormat, DocumentInput
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
