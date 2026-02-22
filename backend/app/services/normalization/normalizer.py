from __future__ import annotations

import re

from app.config import settings
from app.models.document import CanonicalText, DocumentFormat, TextChunk


def normalize_whitespace(text: str) -> str:
    # Collapse runs of whitespace (except newlines) to single space
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove spaces adjacent to newlines
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Sentence splitter using NuPunkt for legal-domain accuracy.

    NuPunkt handles legal citations (e.g., "42 U.S.C. § 1983", "No. 12-345")
    without incorrectly splitting at abbreviation periods.
    Falls back to regex if nupunkt is not installed.
    """
    try:
        from nupunkt import SentenceTokenizer
        tokenizer = SentenceTokenizer()
        sentences = tokenizer.tokenize(text)
        return [s for s in sentences if s.strip()]
    except ImportError:
        # Fallback to regex if nupunkt not installed
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [p for p in parts if p.strip()]


def chunk_text(
    text: str,
    max_chars: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    if max_chars is None:
        max_chars = settings.max_chunk_chars
    if overlap is None:
        overlap = settings.chunk_overlap_chars

    if len(text) <= max_chars:
        return [
            TextChunk(
                text=text,
                start_offset=0,
                end_offset=len(text),
                chunk_index=0,
            )
        ]

    sentences = split_sentences(text)
    chunks: list[TextChunk] = []
    current_sentences: list[str] = []
    current_len = 0
    chunk_start = 0
    position = 0

    for sentence in sentences:
        # Find where this sentence starts in the original text
        sent_start = text.find(sentence, position)
        if sent_start == -1:
            sent_start = position
        sent_end = sent_start + len(sentence)

        if current_len + len(sentence) > max_chars and current_sentences:
            chunk_text_str = " ".join(current_sentences)
            chunk_end = chunk_start + len(chunk_text_str)
            chunks.append(
                TextChunk(
                    text=chunk_text_str,
                    start_offset=chunk_start,
                    end_offset=chunk_end,
                    chunk_index=len(chunks),
                )
            )
            # Overlap: keep last sentences within overlap budget
            overlap_sentences: list[str] = []
            overlap_len = 0
            for s in reversed(current_sentences):
                if overlap_len + len(s) > overlap:
                    break
                overlap_sentences.insert(0, s)
                overlap_len += len(s) + 1  # +1 for space

            current_sentences = overlap_sentences
            current_len = sum(len(s) for s in current_sentences) + max(
                0, len(current_sentences) - 1
            )
            chunk_start = chunk_end - overlap_len if overlap_len > 0 else chunk_end

        current_sentences.append(sentence)
        current_len += len(sentence) + (1 if len(current_sentences) > 1 else 0)
        position = sent_end

    if current_sentences:
        chunk_text_str = " ".join(current_sentences)
        chunks.append(
            TextChunk(
                text=chunk_text_str,
                start_offset=chunk_start,
                end_offset=chunk_start + len(chunk_text_str),
                chunk_index=len(chunks),
            )
        )

    return chunks


def normalize_and_chunk(
    raw_text: str, source_format: DocumentFormat = DocumentFormat.PLAIN_TEXT
) -> CanonicalText:
    normalized = normalize_whitespace(raw_text)
    chunks = chunk_text(normalized)

    # Populate sentence boundaries on each chunk
    for chunk in chunks:
        chunk.sentences = split_sentences(chunk.text)

    return CanonicalText(
        full_text=normalized,
        chunks=chunks,
        source_format=source_format,
    )
