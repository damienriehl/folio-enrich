from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.folio.branch_config import (
    EXCLUDED_BRANCHES,
    get_branch_color,
    get_branch_display_name,
)

logger = logging.getLogger(__name__)


@dataclass
class FOLIOConcept:
    iri: str
    preferred_label: str
    alternative_labels: list[str]
    definition: str
    branch: str
    parent_iris: list[str]


@dataclass
class LabelInfo:
    """A label entry that tracks whether it's a preferred or alternative label."""
    concept: FOLIOConcept
    label_type: str  # "preferred" or "alternative"
    matched_label: str  # The actual label text that matched


class FolioService:
    """Singleton wrapper around folio-python for ontology access."""

    _instance: FolioService | None = None

    def __init__(self) -> None:
        self._folio = None
        self._labels_cache: dict[str, LabelInfo] | None = None
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
        """Build a map from concept IRI to branch display name."""
        if self._folio is None:
            return
        self._branch_map = {}
        try:
            branches = self._folio.get_folio_branches()
            for branch_type, concepts in branches.items():
                # Use display name from branch_config when possible
                branch_key = branch_type.name if hasattr(branch_type, "name") else str(branch_type)
                branch_name = get_branch_display_name(branch_key)
                for concept in concepts:
                    if hasattr(concept, "iri"):
                        self._branch_map[concept.iri] = branch_name
        except Exception:
            logger.warning("Failed to build branch map", exc_info=True)

    def get_all_branches(self) -> list[dict]:
        """Get all non-excluded branches with concept counts and colors."""
        folio = self._get_folio()
        branches_dict = folio.get_folio_branches(max_depth=16)

        result: list[dict] = []
        for ft_key, classes in branches_dict.items():
            branch_key = ft_key.name if hasattr(ft_key, "name") else str(ft_key).split(".")[-1]
            display_name = get_branch_display_name(branch_key)
            if display_name in EXCLUDED_BRANCHES:
                continue
            color = get_branch_color(display_name)
            result.append({
                "name": display_name,
                "color": color,
                "concept_count": len(classes),
            })
        result.sort(key=lambda b: b["name"])
        return result

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

    def get_all_labels(self) -> dict[str, LabelInfo]:
        """Return a mapping of all concept labels to LabelInfo with type metadata.

        Preferred labels take priority: if a label is both a preferred label for
        one concept and an alt label for another, the preferred entry wins.
        """
        if self._labels_cache is not None:
            return self._labels_cache

        folio = self._get_folio()
        labels: dict[str, LabelInfo] = {}

        for concept in folio.classes:
            try:
                fc = self._to_folio_concept(concept)

                # Skip concepts from excluded branches
                if fc.branch in EXCLUDED_BRANCHES:
                    continue

                # Index preferred label (always wins over alt)
                pref = fc.preferred_label
                if pref:
                    key = pref.lower()
                    labels[key] = LabelInfo(
                        concept=fc,
                        label_type="preferred",
                        matched_label=pref,
                    )

                # Index alternative labels (only if not already a preferred label)
                for alt in fc.alternative_labels:
                    if alt:
                        key = alt.lower()
                        if key not in labels or labels[key].label_type != "preferred":
                            labels[key] = LabelInfo(
                                concept=fc,
                                label_type="alternative",
                                matched_label=alt,
                            )
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
