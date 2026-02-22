from __future__ import annotations

from app.models.document import DocumentInput
from app.services.ingestion.base import IngestorBase


class RTFIngestor(IngestorBase):
    """Extract plain text from RTF documents using striprtf."""

    def ingest(self, doc: DocumentInput) -> str:
        from striprtf.striprtf import rtf_to_text

        # Content may be the RTF source text directly or base64-encoded
        content = doc.content
        try:
            # Try to decode as base64 first (file upload)
            import base64
            decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            if decoded.startswith("{\\rtf"):
                content = decoded
        except Exception:
            pass

        return rtf_to_text(content)
