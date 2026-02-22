from __future__ import annotations

from app.models.document import DocumentInput
from app.services.ingestion.base import IngestorBase


class PlainTextIngestor(IngestorBase):
    def ingest(self, doc: DocumentInput) -> str:
        return doc.content
