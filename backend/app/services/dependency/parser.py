from __future__ import annotations

import logging
from dataclasses import dataclass

import spacy

logger = logging.getLogger(__name__)


@dataclass
class SPOTriple:
    subject: str
    predicate: str
    object: str
    sentence: str
    subject_iri: str = ""
    object_iri: str = ""


class DependencyParser:
    """Extract SPO triples from sentences containing FOLIO concepts."""

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        self._nlp = None
        self._model_name = model_name

    def _get_nlp(self):
        if self._nlp is None:
            self._nlp = spacy.load(self._model_name)
        return self._nlp

    def extract_triples(
        self, text: str, concept_spans: list[dict]
    ) -> list[SPOTriple]:
        """Extract SPO triples from text where concepts co-occur in sentences.

        concept_spans: list of {"text": str, "start": int, "end": int, "iri": str}
        """
        nlp = self._get_nlp()
        doc = nlp(text)
        triples = []

        for sent in doc.sents:
            # Find concepts in this sentence
            sent_concepts = [
                cs for cs in concept_spans
                if cs["start"] >= sent.start_char and cs["end"] <= sent.end_char
            ]

            if len(sent_concepts) < 2:
                continue

            # Find the root verb of the sentence
            root = None
            for token in sent:
                if token.dep_ == "ROOT" and token.pos_ == "VERB":
                    root = token
                    break

            if root is None:
                continue

            # Try to extract subject-verb-object patterns
            subjects = []
            objects = []
            for child in root.children:
                if child.dep_ in ("nsubj", "nsubjpass"):
                    subjects.append(child)
                elif child.dep_ in ("dobj", "pobj", "attr", "oprd"):
                    objects.append(child)

            # Match subjects and objects to concept spans
            for subj_token in subjects:
                subj_span = self._find_matching_concept(subj_token, sent_concepts)
                if not subj_span:
                    continue
                for obj_token in objects:
                    obj_span = self._find_matching_concept(obj_token, sent_concepts)
                    if not obj_span:
                        continue
                    triples.append(SPOTriple(
                        subject=subj_span["text"],
                        predicate=root.lemma_,
                        object=obj_span["text"],
                        sentence=sent.text,
                        subject_iri=subj_span.get("iri", ""),
                        object_iri=obj_span.get("iri", ""),
                    ))

        return triples

    def _find_matching_concept(self, token, concept_spans: list[dict]) -> dict | None:
        for cs in concept_spans:
            if (token.idx >= cs["start"] and token.idx < cs["end"]) or \
               (cs["start"] >= token.idx and cs["start"] < token.idx + len(token.text)):
                return cs
        return None
