from __future__ import annotations

import re

from app.models.document import DocumentInput
from app.services.ingestion.base import IngestorBase


class PDFIngestor(IngestorBase):
    def ingest(self, doc: DocumentInput) -> str:
        import pymupdf

        # Content is expected to be base64-encoded PDF bytes for file uploads
        # For now, handle the case where content is the raw text path or bytes
        if doc.filename and doc.filename.endswith(".pdf"):
            # If we get a file path, read it
            try:
                pdf_doc = pymupdf.open(doc.content)
            except Exception:
                # Content might be base64
                import base64

                pdf_bytes = base64.b64decode(doc.content)
                pdf_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        else:
            import base64

            pdf_bytes = base64.b64decode(doc.content)
            pdf_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

        pages = []
        for page in pdf_doc:
            text = page.get_text()
            pages.append(text)
        pdf_doc.close()

        raw_text = "\n\n".join(pages)
        return self._normalize_pdf_text(raw_text)

    def _normalize_pdf_text(self, text: str) -> str:
        # Dehyphenation: rejoin words split across lines
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        # Soft-wrap repair: join lines that don't end with sentence terminators
        text = re.sub(r"(?<![.!?:;\n])\n(?=[a-z])", " ", text)
        # Remove common header/footer patterns (page numbers)
        text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
        return text
