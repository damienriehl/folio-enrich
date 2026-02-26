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
    examples: list[str] | None = None
    notes: list[str] | None = None
    editorial_note: str = ""
    comment: str = ""
    description: str = ""
    source: str = ""
    see_also: list[str] | None = None
    hidden_label: str = ""
    is_defined_by: str = ""


@dataclass
class LabelInfo:
    """A label entry that tracks whether it's a preferred or alternative label."""
    concept: FOLIOConcept
    label_type: str  # "preferred" or "alternative"
    matched_label: str  # The actual label text that matched


@dataclass
class FOLIOProperty:
    iri: str
    label: str  # raw label from ontology (may have prefix)
    clean_label: str  # label with prefix stripped
    preferred_label: str
    alt_labels: list[str]
    clean_alt_labels: list[str]
    definition: str
    examples: list[str] | None = None
    domain_iris: list[str] | None = None
    range_iris: list[str] | None = None
    inverse_of: str | None = None
    sub_property_of: list[str] | None = None


@dataclass
class PropertyLabelInfo:
    """A property label entry tracking whether it's preferred or alternative."""
    prop: FOLIOProperty
    label_type: str  # "preferred" or "alternative"
    matched_label: str


class FolioService:
    """Singleton wrapper around folio-python for ontology access."""

    _instance: FolioService | None = None

    def __init__(self) -> None:
        self._folio = None
        self._labels_cache: dict[str, LabelInfo] | None = None
        self._labels_multi_cache: dict[str, list[LabelInfo]] | None = None
        self._property_labels_cache: dict[str, PropertyLabelInfo] | None = None
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

                # Index hidden label (only if not already preferred or alternative)
                if fc.hidden_label:
                    key = fc.hidden_label.lower()
                    if key not in labels or labels[key].label_type not in ("preferred", "alternative"):
                        labels[key] = LabelInfo(
                            concept=fc,
                            label_type="hidden",
                            matched_label=fc.hidden_label,
                        )
            except Exception:
                continue

        self._labels_cache = labels
        logger.info("Indexed %d FOLIO labels", len(labels))
        return labels

    def get_all_labels_multi(self) -> dict[str, list[LabelInfo]]:
        """Return a mapping of label text to ALL matching concepts.

        Unlike get_all_labels() which keeps only one concept per label,
        this returns every concept that has the label (as preferred, alt, or hidden).
        Within each list, preferred labels sort first; entries are deduplicated by IRI.
        """
        if self._labels_multi_cache is not None:
            return self._labels_multi_cache

        folio = self._get_folio()
        labels: dict[str, list[LabelInfo]] = {}

        for concept in folio.classes:
            try:
                fc = self._to_folio_concept(concept)

                if fc.branch in EXCLUDED_BRANCHES:
                    continue

                # Index preferred label
                pref = fc.preferred_label
                if pref:
                    key = pref.lower()
                    labels.setdefault(key, []).append(LabelInfo(
                        concept=fc, label_type="preferred", matched_label=pref,
                    ))

                # Index alternative labels
                for alt in fc.alternative_labels:
                    if alt:
                        key = alt.lower()
                        labels.setdefault(key, []).append(LabelInfo(
                            concept=fc, label_type="alternative", matched_label=alt,
                        ))

                # Index hidden label
                if fc.hidden_label:
                    key = fc.hidden_label.lower()
                    labels.setdefault(key, []).append(LabelInfo(
                        concept=fc, label_type="hidden", matched_label=fc.hidden_label,
                    ))
            except Exception:
                continue

        # Deduplicate by IRI within each label key; sort preferred first
        _type_order = {"preferred": 0, "alternative": 1, "hidden": 2}
        for key, entries in labels.items():
            seen_iris: set[str] = set()
            deduped: list[LabelInfo] = []
            # Sort so preferred comes first, then dedup by IRI
            entries.sort(key=lambda e: _type_order.get(e.label_type, 9))
            for entry in entries:
                if entry.concept.iri not in seen_iris:
                    seen_iris.add(entry.concept.iri)
                    deduped.append(entry)
            labels[key] = deduped

        self._labels_multi_cache = labels
        total_entries = sum(len(v) for v in labels.values())
        logger.info("Indexed %d FOLIO multi-labels (%d total entries)", len(labels), total_entries)
        return labels

    @staticmethod
    def _strip_prefix(label: str) -> str:
        """Strip namespace prefixes like 'folio:', 'utbms:', 'oasis:' from a label."""
        for prefix in ("folio:", "utbms:", "oasis:"):
            if label.startswith(prefix):
                return label[len(prefix):]
        return label

    def get_all_property_labels(self) -> dict[str, PropertyLabelInfo]:
        """Return a mapping of all property labels to PropertyLabelInfo.

        Preferred labels take priority. Deprecated properties are excluded.
        Labels are lowercased keys with prefixes stripped.
        """
        if self._property_labels_cache is not None:
            return self._property_labels_cache

        folio = self._get_folio()
        labels: dict[str, PropertyLabelInfo] = {}

        for prop in folio.object_properties:
            try:
                fp = self._to_folio_property(prop)

                # Skip deprecated properties
                if "DEPRECATED" in fp.label or fp.label.startswith("ZZZ:"):
                    continue

                # Index clean preferred label
                if fp.clean_label:
                    key = fp.clean_label.lower()
                    labels[key] = PropertyLabelInfo(
                        prop=fp,
                        label_type="preferred",
                        matched_label=fp.clean_label,
                    )

                # Index clean alt labels (only if not already preferred)
                for alt in fp.clean_alt_labels:
                    if alt:
                        akey = alt.lower()
                        if akey not in labels or labels[akey].label_type != "preferred":
                            labels[akey] = PropertyLabelInfo(
                                prop=fp,
                                label_type="alternative",
                                matched_label=alt,
                            )
            except Exception:
                continue

        self._property_labels_cache = labels
        logger.info("Indexed %d FOLIO property labels", len(labels))
        return labels

    def get_property(self, iri: str) -> FOLIOProperty | None:
        """Look up a property by IRI."""
        folio = self._get_folio()
        for prop in folio.object_properties:
            if getattr(prop, "iri", "") == iri:
                return self._to_folio_property(prop)
        return None

    def _to_folio_property(self, prop) -> FOLIOProperty:
        """Convert an OWLObjectProperty to our FOLIOProperty dataclass."""
        raw_label = getattr(prop, "label", None) or getattr(prop, "preferred_label", "") or ""
        clean_label = self._strip_prefix(raw_label)

        # Convert camelCase to spaces (e.g. "hasFigure" → "has Figure")
        # but only for structural labels — leave verbs like "reversed" as-is
        if clean_label and clean_label[0].islower() and any(c.isupper() for c in clean_label[1:]):
            import re
            clean_label = re.sub(r"([a-z])([A-Z])", r"\1 \2", clean_label).lower()

        raw_alts = getattr(prop, "alternative_labels", []) or []
        clean_alts = [self._strip_prefix(a) for a in raw_alts if a]

        definition = getattr(prop, "definition", "") or ""
        examples = getattr(prop, "examples", []) or []
        domain = getattr(prop, "domain", []) or []
        range_ = getattr(prop, "range", []) or []
        inverse_of = getattr(prop, "inverse_of", None)
        sub_prop = getattr(prop, "sub_property_of", []) or []

        return FOLIOProperty(
            iri=getattr(prop, "iri", "") or "",
            label=raw_label,
            clean_label=clean_label,
            preferred_label=raw_label,
            alt_labels=list(raw_alts),
            clean_alt_labels=clean_alts,
            definition=definition,
            examples=list(examples) if examples else None,
            domain_iris=list(domain) if domain else None,
            range_iris=list(range_) if range_ else None,
            inverse_of=inverse_of,
            sub_property_of=list(sub_prop) if sub_prop else None,
        )

    def _to_folio_concept(self, concept) -> FOLIOConcept:
        # preferred_label may be None; fall back to label
        pref_label = getattr(concept, "label", None) or getattr(concept, "preferred_label", "") or ""
        alt_labels = getattr(concept, "alternative_labels", []) or []
        definition = getattr(concept, "definition", "") or ""
        iri = getattr(concept, "iri", "") or ""
        parent_iris = getattr(concept, "sub_class_of", []) or []

        # OWL/SKOS metadata fields
        examples = getattr(concept, "examples", []) or []
        notes = getattr(concept, "notes", []) or []
        editorial_note = getattr(concept, "editorial_note", "") or ""
        comment = getattr(concept, "comment", "") or ""
        description = getattr(concept, "description", "") or ""
        source = getattr(concept, "source", "") or ""
        see_also = getattr(concept, "see_also", []) or []
        hidden_label = getattr(concept, "hidden_label", "") or ""
        is_defined_by = getattr(concept, "is_defined_by", "") or ""

        branch = self._get_branch(iri, list(parent_iris))

        return FOLIOConcept(
            iri=iri,
            preferred_label=pref_label,
            alternative_labels=list(alt_labels),
            definition=definition,
            branch=branch,
            parent_iris=list(parent_iris),
            examples=list(examples) if examples else None,
            notes=list(notes) if notes else None,
            editorial_note=editorial_note,
            comment=comment,
            description=description,
            source=source,
            see_also=list(see_also) if see_also else None,
            hidden_label=hidden_label,
            is_defined_by=is_defined_by,
        )
