from __future__ import annotations

import re

from app.models.document import DocumentInput, TextElement
from app.services.ingestion.base import IngestorBase


class PDFIngestor(IngestorBase):
    def _open_pdf(self, doc: DocumentInput):
        import pymupdf

        if doc.filename and doc.filename.endswith(".pdf"):
            try:
                return pymupdf.open(doc.content)
            except Exception:
                import base64
                pdf_bytes = base64.b64decode(doc.content)
                return pymupdf.open(stream=pdf_bytes, filetype="pdf")
        else:
            import base64
            pdf_bytes = base64.b64decode(doc.content)
            return pymupdf.open(stream=pdf_bytes, filetype="pdf")

    def ingest(self, doc: DocumentInput) -> str:
        text, _ = self.ingest_with_elements(doc)
        return text

    def ingest_with_elements(self, doc: DocumentInput) -> tuple[str, list[TextElement]]:
        pdf_doc = self._open_pdf(doc)
        pages = []
        elements: list[TextElement] = []

        for page_num, page in enumerate(pdf_doc, start=1):
            text = page.get_text()
            pages.append(text)
            # Create a TextElement per page
            for para in text.split("\n\n"):
                para = para.strip()
                if para:
                    elements.append(TextElement(
                        text=para,
                        element_type="paragraph",
                        page=page_num,
                    ))
        pdf_doc.close()

        raw_text = "\n\n".join(pages)
        return self._normalize_pdf_text(raw_text), elements

    def _normalize_pdf_text(self, text: str) -> str:
        # Dehyphenation: rejoin words split across lines
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        # Soft-wrap repair: join lines that don't end with sentence terminators
        text = re.sub(r"(?<![.!?:;\n])\n(?=[a-z])", " ", text)
        # Remove common header/footer patterns (page numbers)
        text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
        return text
