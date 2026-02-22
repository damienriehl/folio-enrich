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

    @classmethod
    def get_instance(cls) -> FolioService:
        if cls._instance is None:
            cls._instance = FolioService()
        return cls._instance

    def _get_folio(self):
        if self._folio is None:
            from folio import Folio

            self._folio = Folio()
            logger.info("FOLIO ontology loaded")
        return self._folio

    def search_by_label(self, label: str, top_k: int = 5) -> list[tuple[FOLIOConcept, float]]:
        folio = self._get_folio()
        results = folio.search_by_label(label)
        output = []
        for concept, score in results[:top_k]:
            output.append((self._to_folio_concept(concept), score))
        return output

    def search_by_prefix(self, prefix: str, top_k: int = 10) -> list[FOLIOConcept]:
        folio = self._get_folio()
        results = folio.search_by_prefix(prefix)
        return [self._to_folio_concept(c) for c, _ in results[:top_k]]

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

        # Iterate through all concepts in the ontology
        for concept_id in folio.get_all_concepts():
            try:
                concept = folio[concept_id]
                fc = self._to_folio_concept(concept)
                # Index by preferred label
                if fc.preferred_label:
                    labels[fc.preferred_label.lower()] = fc
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
        pref_label = getattr(concept, "preferred_label", "") or ""
        alt_labels = getattr(concept, "alternative_labels", []) or []
        definition = getattr(concept, "definition", "") or ""
        iri = getattr(concept, "iri", "") or ""
        parent_iris = getattr(concept, "sub_class_of", []) or []

        # Try to determine branch from hierarchy
        branch = self._infer_branch(pref_label, parent_iris)

        return FOLIOConcept(
            iri=iri,
            preferred_label=pref_label,
            alternative_labels=list(alt_labels),
            definition=definition,
            branch=branch,
            parent_iris=list(parent_iris),
        )

    def _infer_branch(self, label: str, parent_iris: list) -> str:
        # Simple heuristic: branch is often in the top-level parent
        # Full branch inference would walk the hierarchy to root
        return ""
