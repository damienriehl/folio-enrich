"""Pass 2 — Custom regex/spaCy entity extractors for structured entities."""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from functools import partial
from uuid import uuid4

from app.models.annotation import Individual, IndividualClassLink, Span, StageEvent

logger = logging.getLogger(__name__)


class EntityExtractor(ABC):
    """Base class for individual entity extractors."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def folio_label(self) -> str: ...

    @property
    def source(self) -> str:
        return "regex"

    @property
    def confidence(self) -> float:
        return 0.90

    @abstractmethod
    def extract_sync(self, text: str) -> list[Individual]: ...

    def _make_individual(
        self,
        text: str,
        matched: str,
        start: int,
        end: int,
        *,
        name: str | None = None,
        confidence: float | None = None,
        normalized: str | None = None,
        folio_label: str | None = None,
        source: str | None = None,
    ) -> Individual:
        conf = confidence or self.confidence
        return Individual(
            id=str(uuid4()),
            name=name or matched.strip(),
            mention_text=matched,
            individual_type="named_entity",
            span=Span(start=start, end=end, text=matched),
            class_links=[
                IndividualClassLink(
                    folio_label=folio_label or self.folio_label,
                    relationship="instance_of",
                    confidence=conf,
                )
            ],
            confidence=conf,
            source=source or self.source,
            normalized_form=normalized,
            lineage=[
                StageEvent(
                    stage="individual_extraction",
                    action="created",
                    detail=f"{self.source}: {self.name}",
                    confidence=conf,
                )
            ],
        )


class MonetaryAmountExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "monetary_amount"

    @property
    def folio_label(self) -> str:
        return "Monetary Amount"

    @property
    def confidence(self) -> float:
        return 0.93

    _PATTERN = re.compile(
        r"(?:[$€£¥₹])\s*[\d,]+(?:\.\d+)?\s*(?:(?:hundred|thousand|million|billion|trillion|[KMBTkmbt])(?:\s+dollars?)?)?|"
        r"[\d,]+(?:\.\d+)?\s*(?:dollars?|cents?|USD|EUR|GBP|JPY)|"
        r"(?:(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
        r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
        r"million|billion|trillion)[\s-]*)+"
        r"(?:dollars?|cents?|pounds?|euros?)",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            if len(matched) < 2:
                continue
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class DateExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "date"

    @property
    def folio_label(self) -> str:
        return "Date"

    @property
    def confidence(self) -> float:
        return 0.92

    _MONTHS = (
        r"January|February|March|April|May|June|July|August|"
        r"September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    )

    _PATTERN = re.compile(
        rf"(?:(?:{_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}})|"          # January 15, 2023
        rf"(?:\d{{1,2}}\s+(?:{_MONTHS})\.?\s+\d{{4}})|"            # 15 January 2023
        r"(?:\d{1,2}/\d{1,2}/\d{2,4})|"                            # 01/15/2023
        r"(?:\d{4}-\d{2}-\d{2})|"                                  # 2023-01-15
        rf"(?:the\s+\d{{1,2}}(?:st|nd|rd|th)\s+day\s+of\s+(?:{_MONTHS})\.?,?\s+\d{{4}})",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class DurationExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "duration"

    @property
    def folio_label(self) -> str:
        return "Duration"

    @property
    def confidence(self) -> float:
        return 0.90

    _PATTERN = re.compile(
        r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|sixty|ninety)"
        r"(?:\s*\(\d+\))?"  # optional "(6)" clarifier
        r"\s+(?:second|minute|hour|day|week|month|year|decade)s?",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class PercentageExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "percentage"

    @property
    def folio_label(self) -> str:
        return "Percentage"

    @property
    def confidence(self) -> float:
        return 0.93

    _PATTERN = re.compile(
        r"\d+(?:\.\d+)?\s*%|"
        r"(?:one|two|three|four|five|six|seven|eight|nine|ten|"
        r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)"
        r"\s+percent|"
        r"\d+(?:\.\d+)?\s+basis\s+points?",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class CourtExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "court"

    @property
    def folio_label(self) -> str:
        return "Court"

    @property
    def confidence(self) -> float:
        return 0.91

    _PATTERN = re.compile(
        r"(?:Supreme Court of (?:the United States|[A-Z][a-z]+(?: [A-Z][a-z]+)*))|"
        r"(?:United States (?:District|Circuit|Bankruptcy|Tax) Court)|"
        r"(?:(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|"
        r"Eleventh|D\.?C\.?) Circuit)|"
        r"(?:[SNWCE]\.D\.\s*[A-Z][a-z]+\.?)|"  # S.D.N.Y., N.D. Cal.
        r"(?:Court of (?:Appeals?|Common Pleas|Claims|Chancery)(?:\s+(?:for|of)\s+[\w\s]+)?)|"
        r"(?:(?:Superior|District|Circuit|Appellate|Family|Probate|Surrogate(?:'s)?|"
        r"Municipal|Juvenile|Small Claims) Court(?:\s+(?:of|for)\s+[\w\s]+)?)",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class DefinitionExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "definition"

    @property
    def folio_label(self) -> str:
        return "Definition"

    @property
    def confidence(self) -> float:
        return 0.88

    _PATTERN = re.compile(
        r"""(?:[""\u201c])([A-Z][\w\s]{1,60}?)(?:[""\u201d])\s+"""
        r"(?:means?|shall mean|is defined as|refers to|shall refer to|"
        r"has the meaning|hereby defined as)",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            full_match = m.group()
            defined_term = m.group(1).strip() if m.group(1) else full_match.strip()
            results.append(
                self._make_individual(
                    text,
                    full_match.strip(),
                    m.start(),
                    m.end(),
                    name=defined_term,
                )
            )
        return results


class ConditionExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "condition"

    @property
    def folio_label(self) -> str:
        return "Condition"

    @property
    def confidence(self) -> float:
        return 0.85

    _PATTERN = re.compile(
        r"\b(?:if|unless|provided\s+that|subject\s+to|"
        r"on\s+(?:the\s+)?condition\s+that|in\s+the\s+event\s+(?:that)?|"
        r"notwithstanding|except\s+(?:that|where|when|as)|"
        r"contingent\s+upon)\b",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class ConstraintExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "constraint"

    @property
    def folio_label(self) -> str:
        return "Constraint"

    @property
    def confidence(self) -> float:
        return 0.85

    _PATTERN = re.compile(
        r"\b(?:no\s+more\s+than|no\s+less\s+than|no\s+fewer\s+than|"
        r"at\s+least|at\s+most|not\s+to\s+exceed|"
        r"(?:shall|must|will)\s+not\s+exceed|"
        r"up\s+to\s+(?:and\s+including\s+)?\w|"
        r"a\s+maximum\s+of|a\s+minimum\s+of|"
        r"not\s+(?:more|less|fewer)\s+than)\b",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class AddressExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "address"

    @property
    def folio_label(self) -> str:
        return "Address"

    @property
    def confidence(self) -> float:
        return 0.87

    _PATTERN = re.compile(
        r"\d{1,5}\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*"
        r"\s+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|"
        r"Lane|Ln|Way|Court|Ct|Place|Pl|Circle|Cir|Terrace|Ter|Pike|Highway|Hwy)"
        r"\.?"
        r"(?:,?\s+(?:Suite|Ste|Apt|Unit|Floor|Fl|Room|Rm)\.?\s*\d+)?"
        r"(?:,?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)?"
        r"(?:,?\s+[A-Z]{2})?"
        r"(?:\s+\d{5}(?:-\d{4})?)?",
        re.MULTILINE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            if len(matched) < 10:
                continue
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class TrademarkExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "trademark"

    @property
    def folio_label(self) -> str:
        return "Trademark"

    @property
    def confidence(self) -> float:
        return 0.93

    _PATTERN = re.compile(r"[\w]+(?:\s+[\w]+)*\s*[®™]")

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class CopyrightExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "copyright"

    @property
    def folio_label(self) -> str:
        return "Copyright"

    @property
    def confidence(self) -> float:
        return 0.93

    _PATTERN = re.compile(
        r"(?:©|Copyright\s*(?:\(c\)|©)?)\s*\d{4}(?:\s*[-–]\s*\d{4})?"
        r"(?:\s+[A-Z][\w\s,&.]+)?",
        re.IGNORECASE,
    )

    def extract_sync(self, text: str) -> list[Individual]:
        results: list[Individual] = []
        for m in self._PATTERN.finditer(text):
            matched = m.group().strip()
            results.append(self._make_individual(text, matched, m.start(), m.end()))
        return results


class SpaCyPersonExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "person"

    @property
    def folio_label(self) -> str:
        return "Person"

    @property
    def source(self) -> str:
        return "spacy_ner"

    @property
    def confidence(self) -> float:
        return 0.80

    def extract_sync(self, text: str) -> list[Individual]:
        nlp = _get_spacy_nlp()
        if nlp is None:
            return []
        doc = nlp(text)
        results: list[Individual] = []
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                results.append(
                    self._make_individual(
                        text, ent.text, ent.start_char, ent.end_char
                    )
                )
        return results


class SpaCyOrgExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "organization"

    @property
    def folio_label(self) -> str:
        return "Organization"

    @property
    def source(self) -> str:
        return "spacy_ner"

    @property
    def confidence(self) -> float:
        return 0.78

    def extract_sync(self, text: str) -> list[Individual]:
        nlp = _get_spacy_nlp()
        if nlp is None:
            return []
        doc = nlp(text)
        results: list[Individual] = []
        for ent in doc.ents:
            if ent.label_ == "ORG":
                results.append(
                    self._make_individual(
                        text, ent.text, ent.start_char, ent.end_char
                    )
                )
        return results


class SpaCyLocationExtractor(EntityExtractor):
    @property
    def name(self) -> str:
        return "location"

    @property
    def folio_label(self) -> str:
        return "Location"

    @property
    def source(self) -> str:
        return "spacy_ner"

    @property
    def confidence(self) -> float:
        return 0.78

    def extract_sync(self, text: str) -> list[Individual]:
        nlp = _get_spacy_nlp()
        if nlp is None:
            return []
        doc = nlp(text)
        results: list[Individual] = []
        for ent in doc.ents:
            if ent.label_ in ("GPE", "LOC"):
                results.append(
                    self._make_individual(
                        text, ent.text, ent.start_char, ent.end_char
                    )
                )
        return results


# ── spaCy singleton ────────────────────────────────────────────────────

_nlp_instance = None


def _get_spacy_nlp():
    """Lazily load spaCy model (same one used by EntityRuler)."""
    global _nlp_instance
    if _nlp_instance is not None:
        return _nlp_instance
    try:
        import spacy
        _nlp_instance = spacy.load("en_core_web_sm")
        return _nlp_instance
    except Exception:
        logger.warning("spaCy model not available — NER extractors disabled")
        return None


# ── Registry of all extractors ─────────────────────────────────────────

ALL_EXTRACTORS: list[EntityExtractor] = [
    MonetaryAmountExtractor(),
    DateExtractor(),
    DurationExtractor(),
    PercentageExtractor(),
    CourtExtractor(),
    DefinitionExtractor(),
    ConditionExtractor(),
    ConstraintExtractor(),
    AddressExtractor(),
    TrademarkExtractor(),
    CopyrightExtractor(),
    SpaCyPersonExtractor(),
    SpaCyOrgExtractor(),
    SpaCyLocationExtractor(),
]


class EntityExtractorRunner:
    """Runs all entity extractors on text."""

    def __init__(self, extractors: list[EntityExtractor] | None = None) -> None:
        self.extractors = extractors or ALL_EXTRACTORS

    async def extract(self, text: str) -> list[Individual]:
        """Run all extractors in executor (they're sync)."""
        loop = asyncio.get_event_loop()
        all_individuals: list[Individual] = []
        for extractor in self.extractors:
            try:
                individuals = await loop.run_in_executor(
                    None, partial(extractor.extract_sync, text)
                )
                all_individuals.extend(individuals)
            except Exception:
                logger.warning("Extractor %s failed", extractor.name, exc_info=True)
        logger.info(
            "Entity extractors found %d individuals across %d extractors",
            len(all_individuals),
            len(self.extractors),
        )
        return all_individuals
