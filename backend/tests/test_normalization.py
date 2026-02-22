from app.models.document import DocumentFormat
from app.services.normalization.normalizer import (
    chunk_text,
    normalize_and_chunk,
    normalize_whitespace,
    split_sentences,
)


class TestNormalizeWhitespace:
    def test_collapse_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_collapse_tabs(self):
        assert normalize_whitespace("hello\t\tworld") == "hello world"

    def test_preserve_double_newlines(self):
        assert normalize_whitespace("para1\n\npara2") == "para1\n\npara2"

    def test_collapse_triple_newlines(self):
        assert normalize_whitespace("a\n\n\n\nb") == "a\n\nb"

    def test_strip_edges(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_mixed_whitespace(self):
        result = normalize_whitespace("  hello \t world  \n\n\n  next  ")
        assert result == "hello world\n\nnext"


class TestSplitSentences:
    def test_simple_sentences(self):
        result = split_sentences("First sentence. Second sentence. Third sentence.")
        assert len(result) == 3

    def test_single_sentence(self):
        result = split_sentences("Just one sentence.")
        assert len(result) == 1
        assert result[0].strip() == "Just one sentence."

    def test_preserves_abbreviations_lowercase(self):
        # lowercase after period should not split
        result = split_sentences("The U.S. court ruled today.")
        assert len(result) == 1

    def test_legal_citation_usc(self):
        """42 U.S.C. § 1983 should not be split mid-citation."""
        text = "42 U.S.C. § 1983 provides a cause of action. The statute is important."
        result = split_sentences(text)
        # The citation should be in the first sentence, not split
        assert any("42 U.S.C." in s for s in result)

    def test_legal_citation_case_number(self):
        """Case numbers like 'No. 12-345' should not cause splits."""
        text = "See Smith v. Jones, No. 12-345. The court ruled accordingly."
        result = split_sentences(text)
        assert any("No. 12-345" in s or "No." in s for s in result)


class TestChunkText:
    def test_short_text_single_chunk(self):
        text = "Short text."
        chunks = chunk_text(text, max_chars=1000)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].start_offset == 0
        assert chunks[0].end_offset == len(text)
        assert chunks[0].chunk_index == 0

    def test_long_text_multiple_chunks(self):
        sentences = [f"Sentence number {i} is here." for i in range(20)]
        text = " ".join(sentences)
        chunks = chunk_text(text, max_chars=200, overlap=50)
        assert len(chunks) > 1
        # All chunks should have valid offsets
        for chunk in chunks:
            assert chunk.start_offset >= 0
            assert chunk.end_offset > chunk.start_offset
            assert len(chunk.text) > 0

    def test_chunk_indices_sequential(self):
        text = " ".join([f"Sentence {i}." for i in range(30)])
        chunks = chunk_text(text, max_chars=100, overlap=20)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestNormalizeAndChunk:
    def test_returns_canonical_text(self):
        result = normalize_and_chunk("Hello   world.  This is  a test.", DocumentFormat.PLAIN_TEXT)
        assert result.full_text == "Hello world. This is a test."
        assert result.source_format == DocumentFormat.PLAIN_TEXT
        assert len(result.chunks) >= 1

    def test_chunks_cover_text(self):
        text = " ".join([f"Sentence {i} of the document." for i in range(50)])
        result = normalize_and_chunk(text)
        # All chunks should contain text
        for chunk in result.chunks:
            assert len(chunk.text) > 0
