from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FOLIOConcept:
    iri: str
    preferred_label: str
    alternative_labels: list[str]
    definition: str
    branch: str
    parent_iris: list[str]


class FolioService:
    """Singleton wrapper around folio-python for ontology access."""

    _instance: FolioService | None = None

    def __init__(self) -> None:
        self._folio = None
        self._labels_cache: dict[str, FOLIOConcept] | None = None
        self._branch_map: dict[str, str] | None = None

    @classmethod
    def get_instance(cls) -> FolioService:
        if cls._instance is None:
            cls._instance = FolioService()
        return cls._instance

    def _get_folio(self):
        if self._folio is None:
            from folio import FOLIO

            self._folio = FOLIO()
            self._build_branch_map()
            logger.info("FOLIO ontology loaded with %d concepts", len(self._folio.classes))
        return self._folio

    def _build_branch_map(self) -> None:
        """Build a map from concept IRI to branch name."""
        if self._folio is None:
            return
        self._branch_map = {}
        try:
            branches = self._folio.get_folio_branches()
            for branch_type, concepts in branches.items():
                branch_name = branch_type.value if hasattr(branch_type, "value") else str(branch_type)
                for concept in concepts:
                    if hasattr(concept, "iri"):
                        self._branch_map[concept.iri] = branch_name
        except Exception:
            logger.warning("Failed to build branch map", exc_info=True)

    def _get_branch(self, iri: str, parent_iris: list[str]) -> str:
        """Determine the branch for a concept by checking its IRI and ancestors."""
        if self._branch_map is None:
            return ""
        # Direct lookup
        if iri in self._branch_map:
            return self._branch_map[iri]
        # Check parents
        for parent_iri in parent_iris:
            if parent_iri in self._branch_map:
                return self._branch_map[parent_iri]
        # Walk up the hierarchy
        try:
            folio = self._get_folio()
            parents = folio.get_parents(iri)
            for parent in parents:
                if hasattr(parent, "iri") and parent.iri in self._branch_map:
                    # Cache for future lookups
                    self._branch_map[iri] = self._branch_map[parent.iri]
                    return self._branch_map[parent.iri]
        except Exception:
            pass
        return ""

    def search_by_label(self, label: str, top_k: int = 5) -> list[tuple[FOLIOConcept, float]]:
        folio = self._get_folio()
        try:
            results = folio.search_by_label(label)
        except Exception:
            logger.warning("search_by_label failed for '%s'", label, exc_info=True)
            return []
        output = []
        for concept, score in results[:top_k]:
            output.append((self._to_folio_concept(concept), score))
        return output

    def search_by_prefix(self, prefix: str, top_k: int = 10) -> list[FOLIOConcept]:
        folio = self._get_folio()
        try:
            results = folio.search_by_prefix(prefix)
            return [self._to_folio_concept(c) for c, _ in results[:top_k]]
        except Exception:
            logger.warning("search_by_prefix failed for '%s'", prefix, exc_info=True)
            return []

    def get_concept(self, iri: str) -> FOLIOConcept | None:
        folio = self._get_folio()
        try:
            concept = folio[iri]
            return self._to_folio_concept(concept)
        except (KeyError, Exception):
            return None

    def get_all_labels(self) -> dict[str, FOLIOConcept]:
        """Return a mapping of all concept labels (preferred + alternative) to concepts."""
        if self._labels_cache is not None:
            return self._labels_cache

        folio = self._get_folio()
        labels: dict[str, FOLIOConcept] = {}

        for concept in folio.classes:
            try:
                fc = self._to_folio_concept(concept)
                # Index by label
                label = fc.preferred_label
                if label:
                    labels[label.lower()] = fc
                # Index by alternative labels
                for alt in fc.alternative_labels:
                    if alt:
                        labels[alt.lower()] = fc
            except Exception:
                continue

        self._labels_cache = labels
        logger.info("Indexed %d FOLIO labels", len(labels))
        return labels

    def _to_folio_concept(self, concept) -> FOLIOConcept:
        # preferred_label may be None; fall back to label
        pref_label = getattr(concept, "preferred_label", None) or getattr(concept, "label", "") or ""
        alt_labels = getattr(concept, "alternative_labels", []) or []
        definition = getattr(concept, "definition", "") or ""
        iri = getattr(concept, "iri", "") or ""
        parent_iris = getattr(concept, "sub_class_of", []) or []

        branch = self._get_branch(iri, list(parent_iris))

        return FOLIOConcept(
            iri=iri,
            preferred_label=pref_label,
            alternative_labels=list(alt_labels),
            definition=definition,
            branch=branch,
            parent_iris=list(parent_iris),
        )
