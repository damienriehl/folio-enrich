from __future__ import annotations

import abc

from app.models.document import DocumentInput


class IngestorBase(abc.ABC):
    @abc.abstractmethod
    def ingest(self, doc: DocumentInput) -> str:
        """Extract raw text from the document input.

        Returns the extracted plain text content.
        """
