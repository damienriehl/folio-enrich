"""Tests for _resolve_class_link_iris helper in individual_stage."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.annotation import Individual, IndividualClassLink, Span
from app.pipeline.stages.individual_stage import _resolve_class_link_iris


def _make_individual(
    name: str,
    class_links: list[IndividualClassLink],
) -> Individual:
    return Individual(
        name=name,
        mention_text=name,
        span=Span(start=0, end=len(name), text=name),
        class_links=class_links,
    )


def _make_folio_svc(label_to_concept: dict[str, tuple[str, str]]) -> MagicMock:
    """Create a mock FolioService whose get_all_labels returns the given mapping.

    label_to_concept maps label → (iri, branch).  Keys are case-sensitive;
    the mock stores them lowercased to match real FolioService behavior.
    """
    svc = MagicMock()

    # Build the all_labels dict keyed by lowercase label
    all_labels: dict[str, MagicMock] = {}
    for label, (iri, branch) in label_to_concept.items():
        info = MagicMock()
        info.concept.iri = iri
        info.concept.branch = branch
        all_labels[label.lower()] = info

    svc.get_all_labels.return_value = all_labels
    return svc


class TestResolveClassLinkIris:
    """Unit tests for _resolve_class_link_iris."""

    def test_fills_missing_iri(self):
        """Links with folio_label but no folio_iri get resolved."""
        link = IndividualClassLink(folio_label="Statute", confidence=0.8)
        ind = _make_individual("42 U.S.C. § 1983", [link])

        svc = _make_folio_svc({"Statute": ("http://folio.org/Statute", "Area1")})
        _resolve_class_link_iris([ind], svc)

        assert link.folio_iri == "http://folio.org/Statute"
        assert link.branch == "Area1"

    def test_case_insensitive_lookup(self):
        """Label lookup is case-insensitive."""
        link = IndividualClassLink(folio_label="caselaw", confidence=0.9)
        ind = _make_individual("70 N.Y.2d 382", [link])

        svc = _make_folio_svc({"Caselaw": ("http://folio.org/Caselaw", "Legal Authorities")})
        _resolve_class_link_iris([ind], svc)

        assert link.folio_iri == "http://folio.org/Caselaw"

    def test_skips_links_with_existing_iri(self):
        """Links that already have folio_iri are not overwritten."""
        link = IndividualClassLink(
            folio_label="Statute",
            folio_iri="http://existing/iri",
            branch="OrigBranch",
            confidence=0.9,
        )
        ind = _make_individual("42 U.S.C. § 1983", [link])

        svc = _make_folio_svc({"Statute": ("http://folio.org/Statute", "Area1")})
        _resolve_class_link_iris([ind], svc)

        assert link.folio_iri == "http://existing/iri"
        assert link.branch == "OrigBranch"

    def test_skips_links_with_no_label(self):
        """Links with no folio_label are skipped gracefully."""
        link = IndividualClassLink(confidence=0.5)
        ind = _make_individual("something", [link])

        svc = _make_folio_svc({})
        _resolve_class_link_iris([ind], svc)

        assert link.folio_iri is None

    def test_caches_repeated_labels(self):
        """Same label on multiple links uses internal cache (get_all_labels called once)."""
        link1 = IndividualClassLink(folio_label="Person", confidence=0.8)
        link2 = IndividualClassLink(folio_label="Person", confidence=0.7)
        ind1 = _make_individual("John Smith", [link1])
        ind2 = _make_individual("Jane Doe", [link2])

        svc = _make_folio_svc({"Person": ("http://folio.org/Person", "Area2")})
        _resolve_class_link_iris([ind1, ind2], svc)

        assert link1.folio_iri == "http://folio.org/Person"
        assert link2.folio_iri == "http://folio.org/Person"
        # get_all_labels is called once at the start
        svc.get_all_labels.assert_called_once()

    def test_unresolvable_label_leaves_none(self):
        """Labels not found in the ontology remain with folio_iri=None."""
        link = IndividualClassLink(folio_label="UnknownConcept", confidence=0.5)
        ind = _make_individual("mystery", [link])

        svc = _make_folio_svc({})  # No concepts
        _resolve_class_link_iris([ind], svc)

        assert link.folio_iri is None

    def test_preserves_existing_branch(self):
        """If link already has a branch, it's not overwritten."""
        link = IndividualClassLink(
            folio_label="Statute", branch="MyBranch", confidence=0.8
        )
        ind = _make_individual("42 U.S.C. § 1983", [link])

        svc = _make_folio_svc({"Statute": ("http://folio.org/Statute", "Area1")})
        _resolve_class_link_iris([ind], svc)

        assert link.folio_iri == "http://folio.org/Statute"
        assert link.branch == "MyBranch"  # Not overwritten

    def test_empty_individuals_list(self):
        """No-op on empty list (get_all_labels still called but no lookups)."""
        svc = _make_folio_svc({})
        _resolve_class_link_iris([], svc)
        # get_all_labels is called eagerly
        svc.get_all_labels.assert_called_once()

    def test_multiple_class_links_on_one_individual(self):
        """An individual with multiple class links resolves each independently."""
        link_statute = IndividualClassLink(folio_label="Statute", confidence=0.8)
        link_citation = IndividualClassLink(folio_label="Legal Citation", confidence=0.7)
        ind = _make_individual("42 U.S.C. § 1983", [link_statute, link_citation])

        svc = _make_folio_svc({
            "Statute": ("http://folio.org/Statute", "Area1"),
            "Legal Citation": ("http://folio.org/LegalCitation", "Area3"),
        })
        _resolve_class_link_iris([ind], svc)

        assert link_statute.folio_iri == "http://folio.org/Statute"
        assert link_statute.branch == "Area1"
        assert link_citation.folio_iri == "http://folio.org/LegalCitation"
        assert link_citation.branch == "Area3"
