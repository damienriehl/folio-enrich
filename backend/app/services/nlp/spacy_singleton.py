"""Shared spaCy model singletons.

Avoids loading the same model multiple times across pipeline stages.
"""

from __future__ import annotations

import logging
import threading

import spacy
from spacy.language import Language

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_full_nlp: Language | None = None
_tokenizer_nlp: Language | None = None


def get_spacy_nlp() -> Language:
    """Return the full spaCy pipeline (tagger + parser + NER).

    Used by DependencyParser, entity extractors, and other stages that
    need POS tags, dependency trees, or named-entity recognition.
    """
    global _full_nlp
    if _full_nlp is not None:
        return _full_nlp
    with _lock:
        if _full_nlp is not None:
            return _full_nlp
        _full_nlp = spacy.load("en_core_web_sm")
        logger.info("Loaded spaCy full pipeline (en_core_web_sm)")
        return _full_nlp


def get_spacy_tokenizer() -> Language:
    """Return a lightweight spaCy pipeline (tokenizer + lemmatizer only).

    Used by property matcher for verb lemmatisation without the overhead
    of parsing or NER.
    """
    global _tokenizer_nlp
    if _tokenizer_nlp is not None:
        return _tokenizer_nlp
    with _lock:
        if _tokenizer_nlp is not None:
            return _tokenizer_nlp
        _tokenizer_nlp = spacy.load("en_core_web_sm", disable=["ner", "parser"])
        logger.info("Loaded spaCy tokenizer pipeline (en_core_web_sm, no NER/parser)")
        return _tokenizer_nlp
