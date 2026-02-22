from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class DocumentFormat(str, enum.Enum):
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    WORD = "word"


class DocumentInput(BaseModel):
    content: str
    format: DocumentFormat = DocumentFormat.PLAIN_TEXT
    filename: str | None = None


class TextChunk(BaseModel):
    text: str
    start_offset: int
    end_offset: int
    chunk_index: int


class CanonicalText(BaseModel):
    full_text: str
    chunks: list[TextChunk] = Field(default_factory=list)
    source_format: DocumentFormat = DocumentFormat.PLAIN_TEXT
