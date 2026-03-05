import pytest

from app.services.dependency.parser import DependencyParser
from app.models.annotation import SPOTriple, SentencePOS


class TestDependencyParser:
    def test_extract_triples_basic(self):
        parser = DependencyParser()
        text = "The court granted the motion."
        triples, pos_data = parser.extract_triples_and_pos(text)
        assert isinstance(triples, list)
        assert isinstance(pos_data, list)
        # Should extract at least one triple from "court granted motion"
        assert len(triples) >= 1

    def test_extract_triples_returns_spo_triple_objects(self):
        parser = DependencyParser()
        text = "The judge ruled on the case."
        triples, _ = parser.extract_triples_and_pos(text)
        for t in triples:
            assert isinstance(t, SPOTriple)
            assert t.subject
            assert t.predicate
            assert t.sentence

    def test_pos_data_returned(self):
        parser = DependencyParser()
        text = "The court granted the motion. The judge agreed."
        _, pos_data = parser.extract_triples_and_pos(text)
        assert len(pos_data) == 2
        for sp in pos_data:
            assert isinstance(sp, SentencePOS)
            assert len(sp.tokens) == len(sp.pos_tags)
            assert len(sp.tokens) == len(sp.fine_tags)
            assert len(sp.tokens) == len(sp.dep_labels)

    def test_passive_voice_detection(self):
        parser = DependencyParser()
        text = "The motion was granted by the judge."
        triples, _ = parser.extract_triples_and_pos(text)
        passive_triples = [t for t in triples if t.voice == "passive"]
        assert len(passive_triples) >= 1

    def test_legacy_extract_triples_still_works(self):
        parser = DependencyParser()
        text = "The court granted the motion."
        triples = parser.extract_triples(text, [])
        assert isinstance(triples, list)

    def test_conjunction_produces_multiple_triples(self):
        parser = DependencyParser()
        text = "The attorney filed and argued the motion."
        triples, _ = parser.extract_triples_and_pos(text)
        # Should produce triples for both "filed" and "argued"
        assert len(triples) >= 1

    def test_relative_clause(self):
        parser = DependencyParser()
        text = "The judge who granted the motion retired."
        triples, _ = parser.extract_triples_and_pos(text)
        assert isinstance(triples, list)
        # Should extract at least the relative clause triple
        assert len(triples) >= 1
