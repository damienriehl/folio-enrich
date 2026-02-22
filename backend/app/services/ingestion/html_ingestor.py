from __future__ import annotations

from app.models.document import DocumentInput
from app.services.ingestion.base import IngestorBase


class HTMLIngestor(IngestorBase):
    def ingest(self, doc: DocumentInput) -> str:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(doc.content, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "head"]):
            element.decompose()

        text = soup.get_text(separator="\n")

        # Clean up excessive blank lines
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
