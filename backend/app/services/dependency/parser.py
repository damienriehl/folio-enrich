"""Enhanced dependency parser for SVO triple extraction.

Improvements over the original:
- Extracts triples from ALL sentences (no concept gate)
- Passive voice detection and normalization
- Compound verb handling (aux/auxpass chains)
- Conjunction splitting (conj children produce separate triples)
- Relative clause support (relcl)
- Prep + pobj chains ("ruled on the motion")
- Full subtree spans for noun phrases
- POS tag extraction per sentence
"""

from __future__ import annotations

import logging
from uuid import uuid4

from app.models.annotation import SPOTriple, SentencePOS, Span, StageEvent
from app.services.nlp.spacy_singleton import get_spacy_nlp

logger = logging.getLogger(__name__)


class DependencyParser:
    """Extract SPO triples and POS data from text using spaCy dependency parsing."""

    def _get_nlp(self):
        return get_spacy_nlp()

    def extract_triples_and_pos(
        self, text: str
    ) -> tuple[list[SPOTriple], list[SentencePOS]]:
        """Extract SPO triples and POS tags from all sentences.

        Returns (triples, sentence_pos_data).
        """
        nlp = self._get_nlp()
        doc = nlp(text)
        triples: list[SPOTriple] = []
        pos_data: list[SentencePOS] = []

        for sent_idx, sent in enumerate(doc.sents):
            # POS data for every sentence
            pos_data.append(SentencePOS(
                sentence_index=sent_idx,
                start=sent.start_char,
                end=sent.end_char,
                text=sent.text,
                tokens=[t.text for t in sent],
                pos_tags=[t.pos_ for t in sent],
                fine_tags=[t.tag_ for t in sent],
                dep_labels=[t.dep_ for t in sent],
                head_indices=[t.head.i - sent.start for t in sent],
            ))

            # Find root verbs
            for token in sent:
                if token.dep_ == "ROOT" and token.pos_ in ("VERB", "AUX"):
                    sent_triples = self._extract_from_verb(token, sent_idx, sent)
                    triples.extend(sent_triples)

                # Relative clauses: relcl children of nouns produce secondary triples
                if token.dep_ == "relcl" and token.pos_ in ("VERB", "AUX"):
                    relcl_triples = self._extract_from_verb(
                        token, sent_idx, sent, relcl_head=token.head
                    )
                    triples.extend(relcl_triples)

        return triples, pos_data

    def _extract_from_verb(self, verb, sent_idx: int, sent, relcl_head=None) -> list[SPOTriple]:
        """Extract triples rooted at a given verb token."""
        results: list[SPOTriple] = []

        # Detect voice
        is_passive = any(
            child.dep_ in ("nsubjpass", "auxpass") for child in verb.children
        )

        # Build compound predicate text: walk aux/auxpass chain
        predicate_lemma = verb.lemma_
        predicate_text = self._build_compound_verb(verb)

        # Gather subjects and objects
        subjects = []
        objects = []
        prep_objects = []  # (prep_text, obj_token) pairs

        for child in verb.children:
            if child.dep_ in ("nsubj", "nsubjpass"):
                subjects.append(child)
                # Check for conj children of subject (compound subjects)
                for conj in child.children:
                    if conj.dep_ == "conj":
                        subjects.append(conj)
            elif child.dep_ in ("dobj", "attr", "oprd"):
                objects.append(child)
                for conj in child.children:
                    if conj.dep_ == "conj":
                        objects.append(conj)
            elif child.dep_ == "pobj":
                objects.append(child)
            elif child.dep_ == "prep":
                # Prep + pobj chains: "ruled on the motion"
                for pobj in child.children:
                    if pobj.dep_ == "pobj":
                        prep_objects.append((child.text, pobj))
            elif child.dep_ == "agent":
                # Passive voice agent: "by the judge"
                for pobj in child.children:
                    if pobj.dep_ == "pobj":
                        # Agent in passive = logical subject
                        subjects.append(pobj)
            elif child.dep_ == "conj" and child.pos_ in ("VERB", "AUX"):
                # Conjunction splitting: "filed and argued" → separate triples
                conj_triples = self._extract_from_verb(child, sent_idx, sent)
                # Inherit subject from parent verb if conj verb has no subject
                if conj_triples:
                    results.extend(conj_triples)
                elif subjects:
                    # The conj verb has its own objects but no subject
                    conj_objects = [c for c in child.children if c.dep_ in ("dobj", "attr", "oprd", "pobj")]
                    for subj in subjects:
                        for obj in conj_objects:
                            results.append(self._make_triple(
                                subj, child, obj, sent_idx, sent,
                                is_passive=False, predicate_override=child.lemma_,
                            ))

        # For relative clauses, the head noun is an implicit subject
        if relcl_head is not None and not subjects:
            subjects = [relcl_head]

        # If passive and we have agents, they're the real subjects
        # The nsubjpass is the real object
        if is_passive:
            passive_subjects = [c for c in verb.children if c.dep_ == "nsubjpass"]
            agent_subjects = [s for s in subjects if any(
                c.dep_ == "pobj" and c == s for c in s.head.children
            ) or s.dep_ not in ("nsubj", "nsubjpass")]

            if agent_subjects and passive_subjects:
                # Agent found: swap roles
                for agent_subj in agent_subjects:
                    for pass_obj in passive_subjects:
                        results.append(self._make_triple(
                            agent_subj, verb, pass_obj, sent_idx, sent,
                            is_passive=True, normalized=True,
                            predicate_override=predicate_lemma,
                        ))
                return results
            elif passive_subjects:
                # No agent: use passive subject as object, predicate stays
                for pass_subj in passive_subjects:
                    for obj in objects:
                        results.append(self._make_triple(
                            pass_subj, verb, obj, sent_idx, sent,
                            is_passive=True,
                            predicate_override=predicate_lemma,
                        ))
                    # Also try prep_objects
                    for prep_text, pobj in prep_objects:
                        results.append(self._make_triple(
                            pass_subj, verb, pobj, sent_idx, sent,
                            is_passive=True,
                            predicate_override=f"{predicate_lemma} {prep_text}",
                        ))
                if not objects and not prep_objects:
                    # Passive with no explicit object or prep: emit triple with passive_subj as object
                    for pass_subj in passive_subjects:
                        results.append(SPOTriple(
                            id=str(uuid4()),
                            subject="[agent]",
                            predicate=predicate_lemma,
                            object=self._subtree_text(pass_subj),
                            sentence=sent.text,
                            sentence_index=sent_idx,
                            object_span=self._subtree_span(pass_subj),
                            predicate_span=self._token_span(verb),
                            voice="passive",
                            normalized=True,
                            confidence=0.4,
                            source="spacy",
                        ))
                return results

        # Active voice: standard S-V-O
        for subj in subjects:
            for obj in objects:
                results.append(self._make_triple(
                    subj, verb, obj, sent_idx, sent,
                    is_passive=False,
                    predicate_override=predicate_lemma,
                ))
            # Prep + pobj
            for prep_text, pobj in prep_objects:
                results.append(self._make_triple(
                    subj, verb, pobj, sent_idx, sent,
                    is_passive=False,
                    predicate_override=f"{predicate_lemma} {prep_text}",
                ))

        return results

    def _make_triple(
        self, subj_token, verb_token, obj_token,
        sent_idx: int, sent,
        is_passive: bool = False,
        normalized: bool = False,
        predicate_override: str | None = None,
    ) -> SPOTriple:
        """Create an SPOTriple from tokens."""
        return SPOTriple(
            id=str(uuid4()),
            subject=self._subtree_text(subj_token),
            predicate=predicate_override or verb_token.lemma_,
            object=self._subtree_text(obj_token),
            sentence=sent.text,
            sentence_index=sent_idx,
            subject_span=self._subtree_span(subj_token),
            predicate_span=self._token_span(verb_token),
            object_span=self._subtree_span(obj_token),
            voice="passive" if is_passive else "active",
            normalized=normalized,
            confidence=0.7 if not is_passive else 0.6,
            source="spacy",
        )

    @staticmethod
    def _subtree_text(token) -> str:
        """Get full noun phrase text from token's subtree."""
        subtree = sorted(token.subtree, key=lambda t: t.i)
        return " ".join(t.text for t in subtree)

    @staticmethod
    def _subtree_span(token) -> Span:
        """Get character span covering the token's full subtree."""
        subtree = sorted(token.subtree, key=lambda t: t.i)
        start = subtree[0].idx
        last = subtree[-1]
        end = last.idx + len(last.text)
        return Span(
            start=start,
            end=end,
            text=" ".join(t.text for t in subtree),
        )

    @staticmethod
    def _token_span(token) -> Span:
        """Get character span for a single token."""
        return Span(
            start=token.idx,
            end=token.idx + len(token.text),
            text=token.text,
        )

    @staticmethod
    def _build_compound_verb(verb) -> str:
        """Build compound verb text (e.g., 'has been filing' → 'has been filing')."""
        parts = []
        for child in verb.children:
            if child.dep_ in ("aux", "auxpass") and child.i < verb.i:
                parts.append(child.text)
        parts.append(verb.text)
        return " ".join(parts)

    # Legacy compatibility method
    def extract_triples(
        self, text: str, concept_spans: list[dict] | None = None
    ) -> list[SPOTriple]:
        """Extract triples (legacy interface, ignores concept_spans)."""
        triples, _ = self.extract_triples_and_pos(text)
        return triples
