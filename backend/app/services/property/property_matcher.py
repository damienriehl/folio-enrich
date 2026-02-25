"""Aho-Corasick property matcher for FOLIO ObjectProperty labels."""

from __future__ import annotations

import logging
from uuid import uuid4

from app.models.annotation import PropertyAnnotation, Span, StageEvent
from app.services.folio.folio_service import FolioService, PropertyLabelInfo
from app.services.matching.aho_corasick import AhoCorasickMatcher

logger = logging.getLogger(__name__)

# Very conservative stopword list — only the most obvious false-positive words.
# Most single-word verbs like "reversed", "denied", "granted" are kept.
_PROPERTY_STOPWORDS: frozenset[str] = frozenset({
    "not", "and", "near", "equal", "can", "has", "or",
})


class PropertyMatcher:
    """Builds an Aho-Corasick automaton from FOLIO property labels and matches text."""

    def __init__(self) -> None:
        self._matcher = AhoCorasickMatcher()
        self._label_map: dict[str, PropertyLabelInfo] = {}
        self._built = False

    def build(self, folio_service: FolioService | None = None) -> int:
        """Build the automaton from FOLIO property labels. Returns pattern count."""
        svc = folio_service or FolioService.get_instance()
        all_labels = svc.get_all_property_labels()
        self._label_map = all_labels

        count = 0
        for label_key, info in all_labels.items():
            # Skip very short labels
            if len(label_key) <= 2:
                continue

            # Skip obvious stopwords
            if label_key in _PROPERTY_STOPWORDS:
                continue

            self._matcher.add_pattern(label_key, {
                "iri": info.prop.iri,
                "label": info.prop.clean_label,
                "preferred_label": info.prop.preferred_label,
                "definition": info.prop.definition,
                "examples": info.prop.examples,
                "alt_labels": info.prop.clean_alt_labels,
                "domain_iris": info.prop.domain_iris,
                "range_iris": info.prop.range_iris,
                "inverse_of": info.prop.inverse_of,
                "label_type": info.label_type,
                "matched_label": info.matched_label,
            })
            count += 1

        self._matcher.build()
        self._built = True
        logger.info("PropertyMatcher built with %d patterns", count)
        return count

    def match(self, text: str) -> list[PropertyAnnotation]:
        """Search text for property matches, returning PropertyAnnotation objects."""
        if not self._built:
            self.build()

        raw_matches = self._matcher.search(text)
        results: list[PropertyAnnotation] = []

        for m in raw_matches:
            data = m.value
            label_type = data.get("label_type", "preferred")
            confidence = 0.85 if label_type == "preferred" else 0.75

            # Boost multi-word matches
            if " " in m.pattern:
                confidence = min(1.0, confidence + 0.05)

            results.append(PropertyAnnotation(
                id=str(uuid4()),
                property_text=text[m.start:m.end],
                folio_iri=data.get("iri"),
                folio_label=data.get("label"),
                folio_definition=data.get("definition"),
                folio_examples=data.get("examples"),
                folio_alt_labels=data.get("alt_labels"),
                domain_iris=data.get("domain_iris") or [],
                range_iris=data.get("range_iris") or [],
                inverse_of_iri=data.get("inverse_of"),
                span=Span(start=m.start, end=m.end, text=text[m.start:m.end]),
                confidence=confidence,
                source="aho_corasick",
                match_type=label_type,
                lineage=[
                    StageEvent(
                        stage="property_extraction",
                        action="created",
                        detail=f"aho_corasick: matched '{m.pattern}' → {data.get('label')}",
                        confidence=confidence,
                    )
                ],
            ))

        return results

    @property
    def pattern_count(self) -> int:
        return self._matcher.pattern_count
