"""Tests for TextElement model and sentence tracking."""

from app.models.document import TextElement, TextChunk, CanonicalText, DocumentFormat
from app.services.normalization.normalizer import normalize_and_chunk, split_sentences


class TestTextElement:
    def test_text_element_defaults(self):
        elem = TextElement(text="Hello world.")
        assert elem.element_type == "paragraph"
        assert elem.section_path == []
        assert elem.page is None
        assert elem.level is None

    def test_text_element_heading(self):
        elem = TextElement(
            text="Article I",
            element_type="heading",
            section_path=["Article I"],
            level=1,
        )
        assert elem.element_type == "heading"
        assert elem.level == 1

    def test_text_element_with_page(self):
        elem = TextElement(text="Page content", page=3)
        assert elem.page == 3

    def test_text_element_serialization(self):
        elem = TextElement(
            text="Test", element_type="list_item",
            section_path=["Section 1", "Subsection A"],
        )
        data = elem.model_dump()
        assert data["element_type"] == "list_item"
        assert data["section_path"] == ["Section 1", "Subsection A"]
        restored = TextElement(**data)
        assert restored.section_path == ["Section 1", "Subsection A"]


class TestSentenceTracking:
    def test_chunks_have_sentences(self):
        result = normalize_and_chunk(
            "First sentence. Second sentence. Third sentence.",
            DocumentFormat.PLAIN_TEXT,
        )
        assert len(result.chunks) >= 1
        # At least one chunk should have sentences populated
        assert any(len(c.sentences) > 0 for c in result.chunks)

    def test_chunk_sentences_field_default(self):
        chunk = TextChunk(text="test", start_offset=0, end_offset=4, chunk_index=0)
        assert chunk.sentences == []


class TestCanonicalTextElements:
    def test_canonical_text_has_elements_field(self):
        ct = CanonicalText(full_text="test")
        assert ct.elements == []

    def test_canonical_text_with_elements(self):
        elems = [TextElement(text="Heading", element_type="heading", level=1)]
        ct = CanonicalText(full_text="Heading\nBody", elements=elems)
        assert len(ct.elements) == 1
        assert ct.elements[0].element_type == "heading"
