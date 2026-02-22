from __future__ import annotations

import abc

from app.models.document import DocumentInput, TextElement


class IngestorBase(abc.ABC):
    @abc.abstractmethod
    def ingest(self, doc: DocumentInput) -> str:
        """Extract raw text from the document input.

        Returns the extracted plain text content.
        """

    def ingest_with_elements(self, doc: DocumentInput) -> tuple[str, list[TextElement]]:
        """Extract raw text and structural elements from the document.

        Default implementation returns text with no elements.
        Subclasses can override to provide richer structure.
        """
        return self.ingest(doc), []
