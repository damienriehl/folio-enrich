from __future__ import annotations

import logging
from dataclasses import dataclass

import spacy
from spacy.language import Language

from app.services.entity_ruler.pattern_builder import build_patterns
from app.services.folio.folio_service import FOLIOConcept

logger = logging.getLogger(__name__)


@dataclass
class EntityRulerMatch:
    text: str
    start_char: int
    end_char: int
    label: str
    entity_id: str  # FOLIO IRI


class FOLIOEntityRuler:
    """spaCy EntityRuler loaded with FOLIO concept patterns."""

    def __init__(self, nlp: Language | None = None) -> None:
        self._nlp = nlp
        self._loaded = False

    def _get_nlp(self) -> Language:
        if self._nlp is None:
            self._nlp = spacy.blank("en")
        return self._nlp

    def load_patterns(self, concepts: dict[str, FOLIOConcept]) -> None:
        nlp = self._get_nlp()
        patterns = build_patterns(concepts)

        if "entity_ruler" in nlp.pipe_names:
            nlp.remove_pipe("entity_ruler")

        ruler = nlp.add_pipe("entity_ruler", config={"phrase_matcher_attr": "LOWER"})
        ruler.add_patterns(patterns)
        self._loaded = True
        logger.info("EntityRuler loaded with %d patterns", len(patterns))

    def find_matches(self, text: str) -> list[EntityRulerMatch]:
        if not self._loaded:
            return []

        nlp = self._get_nlp()
        doc = nlp(text)
        matches = []
        for ent in doc.ents:
            if ent.label_ == "FOLIO_CONCEPT":
                matches.append(
                    EntityRulerMatch(
                        text=ent.text,
                        start_char=ent.start_char,
                        end_char=ent.end_char,
                        label=ent.label_,
                        entity_id=ent.ent_id_,
                    )
                )
        return matches
