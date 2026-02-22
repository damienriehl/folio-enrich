"""Tests for annotation state lifecycle."""

from app.models.annotation import ConceptMatch


class TestAnnotationStates:
    def test_default_state_is_preliminary(self):
        c = ConceptMatch(concept_text="test")
        assert c.state == "preliminary"

    def test_state_set_to_confirmed(self):
        c = ConceptMatch(concept_text="test", state="confirmed")
        assert c.state == "confirmed"

    def test_state_set_to_rejected(self):
        c = ConceptMatch(concept_text="test", state="rejected")
        assert c.state == "rejected"

    def test_state_survives_serialization(self):
        c = ConceptMatch(concept_text="test", state="confirmed")
        data = c.model_dump()
        assert data["state"] == "confirmed"
        restored = ConceptMatch(**data)
        assert restored.state == "confirmed"

    def test_source_includes_semantic_ruler(self):
        c = ConceptMatch(concept_text="test", source="semantic_ruler")
        assert c.source == "semantic_ruler"
