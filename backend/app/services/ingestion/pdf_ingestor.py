from __future__ import annotations

import re

from app.models.document import DocumentInput, TextElement
from app.services.ingestion.base import IngestorBase

# Detect PDF backend once at import time.
# Prefer PyMuPDF (better extraction quality); fall back to pypdf (pure Python).
try:
    import pymupdf  # noqa: F401

    _PDF_BACKEND = "pymupdf"
except ImportError:
    _PDF_BACKEND = "pypdf"


class PDFIngestor(IngestorBase):
    def _get_pdf_bytes(self, doc: DocumentInput) -> bytes:
        """Decode base64 content to raw PDF bytes."""
        import base64

        return base64.b64decode(doc.content)

    # -- PyMuPDF backend --------------------------------------------------

    def _extract_pages_pymupdf(self, doc: DocumentInput) -> list[tuple[int, str]]:
        import pymupdf

        if doc.filename and doc.filename.endswith(".pdf"):
            try:
                pdf_doc = pymupdf.open(doc.content)
            except Exception:
                pdf_doc = pymupdf.open(stream=self._get_pdf_bytes(doc), filetype="pdf")
        else:
            pdf_doc = pymupdf.open(stream=self._get_pdf_bytes(doc), filetype="pdf")

        pages = []
        for page_num, page in enumerate(pdf_doc, start=1):
            pages.append((page_num, page.get_text()))
        pdf_doc.close()
        return pages

    # -- pypdf backend ----------------------------------------------------

    def _extract_pages_pypdf(self, doc: DocumentInput) -> list[tuple[int, str]]:
        import io

        from pypdf import PdfReader

        pdf_bytes = self._get_pdf_bytes(doc)
        reader = PdfReader(io.BytesIO(pdf_bytes))

        pages = []
        for page_num, page in enumerate(reader.pages, start=1):
            pages.append((page_num, page.extract_text() or ""))
        return pages

    # -- Public interface --------------------------------------------------

    def ingest(self, doc: DocumentInput) -> str:
        text, _ = self.ingest_with_elements(doc)
        return text

    def ingest_with_elements(self, doc: DocumentInput) -> tuple[str, list[TextElement]]:
        if _PDF_BACKEND == "pymupdf":
            pages = self._extract_pages_pymupdf(doc)
        else:
            pages = self._extract_pages_pypdf(doc)

        elements: list[TextElement] = []
        page_texts: list[str] = []

        for page_num, text in pages:
            page_texts.append(text)
            for para in text.split("\n\n"):
                para = para.strip()
                if para:
                    elements.append(
                        TextElement(
                            text=para,
                            element_type="paragraph",
                            page=page_num,
                        )
                    )

        raw_text = "\n\n".join(page_texts)
        return self._normalize_pdf_text(raw_text), elements

    def _normalize_pdf_text(self, text: str) -> str:
        # Dehyphenation: rejoin words split across lines
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        # Soft-wrap repair: join lines that don't end with sentence terminators
        text = re.sub(r"(?<![.!?:;\n])\n(?=[a-z])", " ", text)
        # Remove common header/footer patterns (page numbers)
        text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
        return text
