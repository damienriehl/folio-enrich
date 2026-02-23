"""Tests for concept_detail module: lookup_concept_detail and build_entity_graph."""

import pytest

from app.services.folio.concept_detail import (
    _build_hierarchy_path,
    _extract_iri_hash,
    _get_all_parents,
    build_entity_graph,
    lookup_concept_detail,
)


class FakeOWLClass:
    """Minimal mock of an OWL class."""
    def __init__(
        self,
        iri,
        label,
        definition=None,
        alt_labels=None,
        sub_class_of=None,
        parent_class_of=None,
        see_also=None,
        examples=None,
        translations=None,
    ):
        self.iri = iri
        self.label = label
        self.definition = definition
        self.alternative_labels = alt_labels or []
        self.sub_class_of = sub_class_of or []
        self.parent_class_of = parent_class_of or []
        self.see_also = see_also or []
        self.examples = examples or []
        self.translations = translations or {}


class FakeFOLIO:
    """Mock FOLIO ontology."""
    def __init__(self, concepts: list[FakeOWLClass]):
        self._by_hash = {}
        self.classes = concepts
        for c in concepts:
            h = c.iri.rsplit("/", 1)[-1]
            self._by_hash[h] = c

    def __getitem__(self, key):
        return self._by_hash.get(key)


@pytest.fixture
def mock_folio():
    """Build a small ontology tree:
    ROOT (branch root)
      -> PARENT
           -> CHILD1 (focus)
           -> CHILD2 (sibling)
      -> RELATED (see_also from CHILD1)
    """
    root = FakeOWLClass(
        iri="https://folio.openlegalstandard.org/ROOT",
        label="Area of Law",
        sub_class_of=["http://www.w3.org/2002/07/owl#Thing"],
        parent_class_of=["https://folio.openlegalstandard.org/PARENT"],
    )
    parent = FakeOWLClass(
        iri="https://folio.openlegalstandard.org/PARENT",
        label="Criminal Law",
        definition="Law relating to crime",
        sub_class_of=["https://folio.openlegalstandard.org/ROOT"],
        parent_class_of=[
            "https://folio.openlegalstandard.org/CHILD1",
            "https://folio.openlegalstandard.org/CHILD2",
        ],
    )
    child1 = FakeOWLClass(
        iri="https://folio.openlegalstandard.org/CHILD1",
        label="DUI Defense",
        definition="Defense against driving under influence charges",
        alt_labels=["DWI Defense"],
        sub_class_of=["https://folio.openlegalstandard.org/PARENT"],
        see_also=["https://folio.openlegalstandard.org/RELATED"],
        examples=["First-time DUI case"],
        translations={"es": "Defensa por DUI", "fr": "Defense DUI"},
    )
    child2 = FakeOWLClass(
        iri="https://folio.openlegalstandard.org/CHILD2",
        label="Assault Defense",
        sub_class_of=["https://folio.openlegalstandard.org/PARENT"],
    )
    related = FakeOWLClass(
        iri="https://folio.openlegalstandard.org/RELATED",
        label="Traffic Violations",
        sub_class_of=["https://folio.openlegalstandard.org/ROOT"],
    )
    return FakeFOLIO([root, parent, child1, child2, related])


class TestExtractIriHash:
    def test_extracts_hash(self):
        assert _extract_iri_hash("https://folio.openlegalstandard.org/ABC123") == "ABC123"

    def test_no_slash(self):
        assert _extract_iri_hash("ABC123") == "ABC123"


class TestLookupConceptDetail:
    def test_returns_none_for_unknown(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "NONEXISTENT")
        assert result is None

    def test_returns_basic_info(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "CHILD1")
        assert result is not None
        assert result.label == "DUI Defense"
        assert result.iri_hash == "CHILD1"
        assert result.definition == "Defense against driving under influence charges"

    def test_returns_synonyms(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "CHILD1")
        assert "DWI Defense" in result.synonyms

    def test_returns_children(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "PARENT")
        assert len(result.children) == 2
        child_labels = {c.label for c in result.children}
        assert "DUI Defense" in child_labels
        assert "Assault Defense" in child_labels

    def test_returns_siblings(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "CHILD1")
        assert len(result.siblings) == 1
        assert result.siblings[0].label == "Assault Defense"

    def test_returns_related(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "CHILD1")
        assert len(result.related) == 1
        assert result.related[0].label == "Traffic Violations"

    def test_returns_translations(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "CHILD1")
        assert result.translations.get("es") == "Defensa por DUI"
        assert result.translations.get("fr") == "Defense DUI"

    def test_returns_examples(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "CHILD1")
        assert "First-time DUI case" in result.examples

    def test_has_branch_color(self, mock_folio):
        result = lookup_concept_detail(mock_folio, "CHILD1")
        assert result.branch_color  # Should have some color


class TestBuildEntityGraph:
    def test_returns_none_for_unknown(self, mock_folio):
        result = build_entity_graph(mock_folio, "NONEXISTENT")
        assert result is None

    def test_builds_graph_around_focus(self, mock_folio):
        result = build_entity_graph(mock_folio, "CHILD1", ancestors_depth=2, descendants_depth=1)
        assert result is not None
        assert result.focus_iri_hash == "CHILD1"
        assert result.focus_label == "DUI Defense"

    def test_graph_has_nodes_and_edges(self, mock_folio):
        result = build_entity_graph(mock_folio, "CHILD1")
        assert len(result.nodes) >= 1
        # Focus node should be present
        focus_nodes = [n for n in result.nodes if n.is_focus]
        assert len(focus_nodes) == 1
        assert focus_nodes[0].label == "DUI Defense"

    def test_graph_includes_ancestors(self, mock_folio):
        result = build_entity_graph(mock_folio, "CHILD1", ancestors_depth=2)
        node_labels = {n.label for n in result.nodes}
        assert "Criminal Law" in node_labels  # parent

    def test_graph_includes_see_also(self, mock_folio):
        result = build_entity_graph(mock_folio, "CHILD1", include_see_also=True)
        node_labels = {n.label for n in result.nodes}
        assert "Traffic Violations" in node_labels

    def test_graph_without_see_also(self, mock_folio):
        result = build_entity_graph(mock_folio, "CHILD1", include_see_also=False)
        see_also_edges = [e for e in result.edges if e.edge_type == "seeAlso"]
        assert len(see_also_edges) == 0

    def test_respects_max_nodes(self, mock_folio):
        result = build_entity_graph(mock_folio, "CHILD1", max_nodes=2)
        assert len(result.nodes) <= 2

    def test_edges_have_valid_format(self, mock_folio):
        result = build_entity_graph(mock_folio, "CHILD1")
        for edge in result.edges:
            assert edge.source
            assert edge.target
            assert edge.edge_type in ("subClassOf", "seeAlso")


class TestGetAllParents:
    def test_returns_parents(self, mock_folio):
        parents = _get_all_parents(mock_folio, "CHILD1")
        assert len(parents) == 1
        assert parents[0].label == "Criminal Law"

    def test_returns_empty_for_root(self, mock_folio):
        parents = _get_all_parents(mock_folio, "ROOT")
        # ROOT's parent is owl:Thing, which is filtered out
        assert len(parents) == 0

    def test_returns_empty_for_unknown(self, mock_folio):
        parents = _get_all_parents(mock_folio, "NONEXISTENT")
        assert len(parents) == 0
