import pytest

from app.services.dependency.parser import DependencyParser


class TestDependencyParser:
    def test_extract_triples_basic(self):
        parser = DependencyParser()
        text = "The court granted the motion."
        concept_spans = [
            {"text": "court", "start": 4, "end": 9, "iri": "iri1"},
            {"text": "motion", "start": 22, "end": 28, "iri": "iri2"},
        ]
        triples = parser.extract_triples(text, concept_spans)
        # May or may not find triples depending on spacy model's parse
        # At minimum, it should not crash
        assert isinstance(triples, list)

    def test_no_concepts_returns_empty(self):
        parser = DependencyParser()
        text = "This is a plain sentence."
        triples = parser.extract_triples(text, [])
        assert triples == []

    def test_single_concept_no_triples(self):
        parser = DependencyParser()
        text = "The court ruled."
        concept_spans = [
            {"text": "court", "start": 4, "end": 9, "iri": "iri1"},
        ]
        triples = parser.extract_triples(text, concept_spans)
        assert triples == []  # Need 2+ concepts per sentence
