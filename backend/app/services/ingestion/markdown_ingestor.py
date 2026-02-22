from __future__ import annotations

import re

from app.models.document import DocumentInput
from app.services.ingestion.base import IngestorBase


class MarkdownIngestor(IngestorBase):
    def ingest(self, doc: DocumentInput) -> str:
        text = doc.content
        # Strip markdown formatting but preserve structure
        # Remove headers markers but keep text
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove bold/italic markers
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
        # Remove link formatting but keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove image formatting
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        # Remove inline code backticks
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Remove horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        # Remove list markers
        text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
        return text.strip()
