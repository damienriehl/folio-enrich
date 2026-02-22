from app.models.document import DocumentFormat, DocumentInput
from app.services.ingestion.html_ingestor import HTMLIngestor
from app.services.ingestion.markdown_ingestor import MarkdownIngestor


class TestHTMLIngestor:
    def test_strips_tags(self):
        doc = DocumentInput(
            content="<html><body><p>The court ruled.</p><p>Damages awarded.</p></body></html>",
            format=DocumentFormat.HTML,
        )
        ingestor = HTMLIngestor()
        text = ingestor.ingest(doc)
        assert "The court ruled." in text
        assert "Damages awarded." in text
        assert "<p>" not in text

    def test_removes_scripts_and_styles(self):
        doc = DocumentInput(
            content="<html><head><style>body{}</style></head><body><script>alert('x')</script><p>Content</p></body></html>",
            format=DocumentFormat.HTML,
        )
        ingestor = HTMLIngestor()
        text = ingestor.ingest(doc)
        assert "Content" in text
        assert "alert" not in text
        assert "body{}" not in text

    def test_preserves_text_structure(self):
        doc = DocumentInput(
            content="<h1>Title</h1><p>First paragraph.</p><p>Second paragraph.</p>",
            format=DocumentFormat.HTML,
        )
        ingestor = HTMLIngestor()
        text = ingestor.ingest(doc)
        assert "Title" in text
        assert "First paragraph." in text


class TestMarkdownIngestor:
    def test_strips_headers(self):
        doc = DocumentInput(content="# Title\n\nSome content.", format=DocumentFormat.MARKDOWN)
        ingestor = MarkdownIngestor()
        text = ingestor.ingest(doc)
        assert "Title" in text
        assert "#" not in text

    def test_strips_bold_italic(self):
        doc = DocumentInput(content="This is **bold** and *italic*.", format=DocumentFormat.MARKDOWN)
        ingestor = MarkdownIngestor()
        text = ingestor.ingest(doc)
        assert "bold" in text
        assert "italic" in text
        assert "**" not in text
        assert text.count("*") == 0

    def test_strips_links(self):
        doc = DocumentInput(content="Visit [example](https://example.com).", format=DocumentFormat.MARKDOWN)
        ingestor = MarkdownIngestor()
        text = ingestor.ingest(doc)
        assert "example" in text
        assert "https://" not in text

    def test_strips_list_markers(self):
        doc = DocumentInput(content="- Item 1\n- Item 2\n1. Numbered", format=DocumentFormat.MARKDOWN)
        ingestor = MarkdownIngestor()
        text = ingestor.ingest(doc)
        assert "Item 1" in text
        assert "Numbered" in text
