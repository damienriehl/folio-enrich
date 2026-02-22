from __future__ import annotations

from app.models.document import DocumentFormat, DocumentInput
from app.services.ingestion.base import IngestorBase
from app.services.ingestion.html_ingestor import HTMLIngestor
from app.services.ingestion.markdown_ingestor import MarkdownIngestor
from app.services.ingestion.pdf_ingestor import PDFIngestor
from app.services.ingestion.plain_text import PlainTextIngestor
from app.services.ingestion.word_ingestor import WordIngestor

_INGESTORS: dict[DocumentFormat, type[IngestorBase]] = {
    DocumentFormat.PLAIN_TEXT: PlainTextIngestor,
    DocumentFormat.PDF: PDFIngestor,
    DocumentFormat.WORD: WordIngestor,
    DocumentFormat.HTML: HTMLIngestor,
    DocumentFormat.MARKDOWN: MarkdownIngestor,
}


def register_ingestor(fmt: DocumentFormat, cls: type[IngestorBase]) -> None:
    _INGESTORS[fmt] = cls


def get_ingestor(fmt: DocumentFormat) -> IngestorBase:
    cls = _INGESTORS.get(fmt)
    if cls is None:
        raise ValueError(f"No ingestor registered for format: {fmt}")
    return cls()


def detect_format(filename: str | None, content: str) -> DocumentFormat:
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        ext_map = {
            "txt": DocumentFormat.PLAIN_TEXT,
            "md": DocumentFormat.MARKDOWN,
            "html": DocumentFormat.HTML,
            "htm": DocumentFormat.HTML,
            "pdf": DocumentFormat.PDF,
            "docx": DocumentFormat.WORD,
            "doc": DocumentFormat.WORD,
        }
        if ext in ext_map:
            return ext_map[ext]

    # Heuristic detection for content without filename
    stripped = content.strip()
    if stripped.startswith("<!") or stripped.startswith("<html"):
        return DocumentFormat.HTML
    if stripped.startswith("# ") or "\n## " in stripped:
        return DocumentFormat.MARKDOWN

    return DocumentFormat.PLAIN_TEXT


def ingest(doc: DocumentInput) -> str:
    ingestor = get_ingestor(doc.format)
    return ingestor.ingest(doc)
