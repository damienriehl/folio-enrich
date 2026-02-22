import pytest

from app.services.folio.folio_service import FOLIOConcept, FolioService
from app.services.folio.resolver import ConceptResolver


class FakeFolioService(FolioService):
    """Fake FOLIO service that returns pre-configured results without loading the ontology."""

    def __init__(self):
        super().__init__()
        self._fake_concepts = {
            "breach of contract": FOLIOConcept(
                iri="https://folio.openlegalstandard.org/R001",
                preferred_label="Breach of Contract",
                alternative_labels=["contract breach"],
                definition="Failure to perform contractual obligations",
                branch="Legal Concepts",
                parent_iris=[],
            ),
            "damages": FOLIOConcept(
                iri="https://folio.openlegalstandard.org/R002",
                preferred_label="Damages",
                alternative_labels=["monetary damages"],
                definition="Monetary compensation for loss or injury",
                branch="Legal Concepts",
                parent_iris=[],
            ),
            "court": FOLIOConcept(
                iri="https://folio.openlegalstandard.org/R003",
                preferred_label="Court",
                alternative_labels=["tribunal"],
                definition="A tribunal for the administration of justice",
                branch="Legal Entities",
                parent_iris=[],
            ),
        }

    def search_by_label(self, label: str, top_k: int = 5) -> list[tuple[FOLIOConcept, float]]:
        key = label.lower()
        if key in self._fake_concepts:
            return [(self._fake_concepts[key], 0.95)]
        # Partial match
        for k, v in self._fake_concepts.items():
            if key in k or k in key:
                return [(v, 0.7)]
        return []


class TestConceptResolver:
    def test_resolve_known_concept(self):
        resolver = ConceptResolver(FakeFolioService())
        result = resolver.resolve("breach of contract", "Legal Concepts", 0.9)
        assert result is not None
        assert result.folio_concept.iri == "https://folio.openlegalstandard.org/R001"
        assert result.folio_concept.preferred_label == "Breach of Contract"

    def test_resolve_unknown_concept(self):
        resolver = ConceptResolver(FakeFolioService())
        result = resolver.resolve("quantum computing", "Technology")
        assert result is None

    def test_resolve_caches_results(self):
        resolver = ConceptResolver(FakeFolioService())
        result1 = resolver.resolve("damages")
        result2 = resolver.resolve("damages")
        assert result1 is result2
        assert resolver.cache_size == 1

    def test_resolve_batch(self):
        resolver = ConceptResolver(FakeFolioService())
        results = resolver.resolve_batch([
            {"concept_text": "breach of contract", "branch": "Legal Concepts", "confidence": 0.9},
            {"concept_text": "damages", "branch": "", "confidence": 0.8},
            {"concept_text": "unknown concept xyz", "branch": "", "confidence": 0.5},
        ])
        assert len(results) == 3
        assert results[0] is not None
        assert results[1] is not None
        assert results[2] is None

    def test_cache_is_case_insensitive(self):
        resolver = ConceptResolver(FakeFolioService())
        r1 = resolver.resolve("Court")
        r2 = resolver.resolve("court")
        assert r1 is r2
        assert resolver.cache_size == 1
