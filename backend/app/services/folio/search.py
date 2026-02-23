"""Multi-strategy FOLIO search with word-overlap scoring.

Ported from folio-mapper: 7-strategy search across label, prefix, definition,
sub-phrases, content words, legal expansions, and stem prefix matching.
"""

from __future__ import annotations

import logging
import re

from app.services.folio.branch_config import (
    EXCLUDED_BRANCHES,
    get_branch_color,
)

logger = logging.getLogger(__name__)

# Words too common to be useful for individual search or scoring
SEARCH_STOPWORDS = frozenset({
    "a", "an", "the", "of", "and", "or", "in", "for", "to", "with", "by", "on", "at",
    "is", "are", "was", "were", "be", "been", "being",
    "not", "no", "has", "have", "had", "do", "does", "did",
    "this", "that", "it", "its", "their", "other", "such", "than",
    "law", "legal", "type", "types", "general",
})

# Domain-aware expansions: common legal content words -> FOLIO label suffixes.
LEGAL_TERM_EXPANSIONS: dict[str, list[str]] = {
    # Core practice types
    "litigation": ["practice", "service"],
    "transactional": ["practice", "service"],
    "transaction": ["practice", "service"],
    "transactions": ["practice", "service"],
    "regulatory": ["practice", "compliance"],
    "compliance": ["practice", "service"],
    "advisory": ["practice", "service"],
    # Dispute resolution
    "dispute": ["service", "resolution"],
    "disputes": ["service", "resolution"],
    "mediation": ["service"],
    "arbitration": ["service"],
    "negotiation": ["service"],
    "settlement": ["service", "practice"],
    "appellate": ["practice", "service"],
    "trial": ["practice", "service"],
    "appeals": ["practice", "service"],
    # Enforcement & prosecution
    "prosecution": ["service"],
    "enforcement": ["service", "action"],
    "investigation": ["service"],
    # Practice areas
    "corporate": ["practice", "service", "law"],
    "employment": ["practice", "service", "law"],
    "intellectual": ["property", "practice"],
    "bankruptcy": ["practice", "service", "law"],
    "family": ["practice", "law"],
    "immigration": ["practice", "service", "law"],
    "environmental": ["practice", "law", "compliance"],
    "antitrust": ["practice", "law", "compliance"],
    "tax": ["practice", "service", "law"],
    "real": ["estate", "property"],
    "estate": ["planning", "practice", "law"],
    # Advisory & counseling
    "counsel": ["service", "practice"],
    "counseling": ["service", "practice"],
    "consulting": ["service", "practice"],
    # Recovery & collections
    "collection": ["service", "practice"],
    "recovery": ["service", "practice"],
    "foreclosure": ["service", "practice"],
    # Investigation & due diligence
    "discovery": ["service", "practice"],
    "diligence": ["service", "practice"],
    "audit": ["service", "practice"],
    # Documentation & filing
    "drafting": ["service", "practice"],
    "documentation": ["service", "practice"],
    "filing": ["service", "practice"],
    # Strategy & planning
    "strategy": ["service", "practice"],
    "planning": ["service", "practice"],
    "risk": ["service", "management"],
    "structuring": ["service", "practice"],
}


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase alphabetic tokens (2+ chars)."""
    return [w.lower() for w in re.findall(r"[a-zA-Z]+", text) if len(w) >= 2]


def _content_words(text: str) -> set[str]:
    """Extract meaningful (non-stopword) words from text."""
    return {w for w in _tokenize(text) if w not in SEARCH_STOPWORDS}


def _word_overlap(query_words: set[str], target_words: set[str]) -> float:
    """Bidirectional word overlap with prefix-match and morphological stem credit."""
    if not query_words or not target_words:
        return 0.0

    def _directional_overlap(source: set[str], dest: set[str]) -> float:
        matched = 0.0
        for sw in source:
            best = 0.0
            for dw in dest:
                if sw == dw:
                    best = 1.0
                    break
                elif len(sw) >= 3 and len(dw) >= 3:
                    if sw.startswith(dw) or dw.startswith(sw):
                        best = max(best, 0.8)
                    elif len(sw) >= 5 and len(dw) >= 5:
                        pfx = 0
                        for c1, c2 in zip(sw, dw):
                            if c1 == c2:
                                pfx += 1
                            else:
                                break
                        if pfx >= 4 and pfx / min(len(sw), len(dw)) >= 0.7:
                            best = max(best, 0.7)
            matched += best
        return matched / len(source)

    forward = _directional_overlap(query_words, target_words)

    reverse = 0.0
    if len(target_words) >= 2:
        reverse = _directional_overlap(target_words, query_words) * 0.75

    return max(forward, reverse)


def _compute_relevance_score(
    query_content: set[str],
    query_full: str,
    label: str,
    definition: str | None,
    synonyms: list[str],
) -> float:
    """Score 0-100 based on word overlap between query and candidate."""
    if not label:
        return 0.0

    query_lower = query_full.lower().strip()
    label_lower = label.lower()

    # Exact match
    if query_lower == label_lower:
        return 99.0

    label_content = _content_words(label)

    # --- Label scoring ---
    label_score = 0.0
    if len(query_lower) >= 4 and query_lower in label_lower:
        label_score = 92.0
    elif (
        len(label_lower) >= 4
        and label_lower in query_lower
        and len(label_lower) / len(query_lower) > 0.3
    ):
        label_score = 88.0
    overlap = _word_overlap(query_content, label_content)
    if overlap > 0:
        label_score = max(label_score, overlap * 88)

    # --- Synonym scoring ---
    syn_score = 0.0
    for syn in synonyms:
        syn_content = _content_words(syn)
        s_overlap = _word_overlap(query_content, syn_content)
        if s_overlap > 0:
            syn_score = max(syn_score, s_overlap * 82)

    # --- Definition scoring ---
    def_score = 0.0
    if definition:
        def_lower = definition.lower()
        if query_lower in def_lower:
            def_score = 60.0
        def_content = _content_words(definition)
        d_overlap = _word_overlap(query_content, def_content)
        if d_overlap > 0:
            def_score = max(def_score, d_overlap * 55)

    # Combine: best of label/synonym, with small definition boost
    primary = max(label_score, syn_score)
    if primary > 0:
        final = primary + min(def_score * 0.12, 8)
    else:
        final = def_score

    return round(min(final, 99.0), 1)


def _generate_search_terms(term: str) -> list[str]:
    """Generate search terms: full phrase, sub-phrases, individual content words."""
    words = _tokenize(term)
    content = _content_words(term)

    terms = [term]  # Always search full phrase

    # Sub-phrases (windows of 2..n-1 consecutive words)
    if len(words) >= 3:
        for n in range(len(words) - 1, 1, -1):
            for i in range(len(words) - n + 1):
                sub = " ".join(words[i : i + n])
                if _content_words(sub):
                    terms.append(sub)

    # Individual content words (3+ chars)
    for w in sorted(content, key=len, reverse=True):
        if len(w) >= 3:
            terms.append(w)

    # Domain-aware expansions
    for w in content:
        suffixes = LEGAL_TERM_EXPANSIONS.get(w)
        if suffixes:
            for suffix in suffixes:
                terms.append(f"{w} {suffix}")

    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for t in terms:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            result.append(t)

    return result


def _extract_iri_hash(iri: str) -> str:
    """Extract the hash portion from a full FOLIO IRI."""
    return iri.rsplit("/", 1)[-1]


def multi_strategy_search(
    folio,
    text: str,
    branch: str | None = None,
    top_n: int = 5,
    threshold: float = 30.0,
    get_branch_fn=None,
) -> list[dict]:
    """Search FOLIO using multi-strategy search with word-overlap scoring.

    Args:
        folio: FOLIO instance from folio-python.
        text: The concept text to search for.
        branch: Optional branch filter (display name).
        top_n: Maximum results to return.
        threshold: Minimum score (0-100) for inclusion.
        get_branch_fn: Optional callable(folio, iri_hash) -> branch_name.

    Returns:
        List of dicts with keys: label, iri, iri_hash, definition, synonyms,
        branch, branch_color, score.
    """
    content_words = _content_words(text)
    if not content_words:
        content_words = set(_tokenize(text))

    search_terms = _generate_search_terms(text)

    # Phase 1: Gather raw candidates from multiple search strategies
    raw: dict[str, object] = {}  # iri_hash -> OWLClass

    for st in search_terms:
        # Label search (fuzzy)
        try:
            for owl_class, _ in folio.search_by_label(st, include_alt_labels=True, limit=25):
                h = _extract_iri_hash(owl_class.iri)
                if h not in raw:
                    raw[h] = owl_class
        except Exception:
            pass

        # Prefix search
        if len(st) >= 3:
            try:
                for owl_class in folio.search_by_prefix(st):
                    h = _extract_iri_hash(owl_class.iri)
                    if h not in raw:
                        raw[h] = owl_class
            except Exception:
                pass

    # Stem prefix search
    for cw in content_words:
        if len(cw) >= 6:
            stem = cw[: len(cw) - 2]
            try:
                for owl_class in folio.search_by_prefix(stem)[:50]:
                    h = _extract_iri_hash(owl_class.iri)
                    if h not in raw:
                        raw[h] = owl_class
            except Exception:
                pass

    # Definition search
    def_terms = [text]
    cw_phrase = " ".join(sorted(content_words))
    if cw_phrase.lower() != text.lower():
        def_terms.append(cw_phrase)
    for st in def_terms:
        if len(st) >= 3:
            try:
                for owl_class, _ in folio.search_by_definition(st, limit=20):
                    h = _extract_iri_hash(owl_class.iri)
                    if h not in raw:
                        raw[h] = owl_class
            except Exception:
                pass

    logger.debug("multi_strategy_search(%r): %d raw candidates", text, len(raw))

    # Phase 2: Re-score all candidates
    min_score = threshold
    scored: list[tuple[str, object, float]] = []

    for iri_hash, owl_class in raw.items():
        score = _compute_relevance_score(
            content_words,
            text,
            owl_class.label or iri_hash,
            owl_class.definition,
            owl_class.alternative_labels or [],
        )
        if score >= min_score:
            scored.append((iri_hash, owl_class, score))

    # Phase 2.1: Expansion re-scoring
    expansion_queries: list[tuple[set[str], str]] = []
    for w in content_words:
        suffixes = LEGAL_TERM_EXPANSIONS.get(w)
        if suffixes:
            for suffix in suffixes:
                eq = f"{w} {suffix}"
                expansion_queries.append((_content_words(eq), eq))

    if expansion_queries:
        best_scores: dict[str, float] = {h: s for h, _, s in scored}
        for iri_hash, owl_class in raw.items():
            for eq_content, eq_full in expansion_queries:
                exp_score = _compute_relevance_score(
                    eq_content,
                    eq_full,
                    owl_class.label or iri_hash,
                    owl_class.definition,
                    owl_class.alternative_labels or [],
                )
                if exp_score >= min_score and exp_score > best_scores.get(iri_hash, 0):
                    best_scores[iri_hash] = exp_score

        scored_map: dict[str, tuple[str, object, float]] = {
            h: (h, c, s) for h, c, s in scored
        }
        for iri_hash, new_score in best_scores.items():
            if iri_hash in scored_map:
                _, owl_class, old_score = scored_map[iri_hash]
                if new_score > old_score:
                    scored_map[iri_hash] = (iri_hash, owl_class, new_score)
            elif new_score >= min_score:
                scored_map[iri_hash] = (iri_hash, raw[iri_hash], new_score)
        scored = list(scored_map.values())

    # Phase 2.5: Surface ancestor concepts
    ancestor_scores: dict[str, float] = {}
    for iri_hash, owl_class, score in scored:
        if score < 50:
            continue
        current = owl_class
        for depth in range(1, 4):
            if not current or not getattr(current, "sub_class_of", None):
                break
            parent_hash = _extract_iri_hash(current.sub_class_of[0])
            if parent_hash not in raw:
                parent_score = score * (0.6 ** depth)
                if parent_score >= min_score:
                    ancestor_scores[parent_hash] = max(
                        ancestor_scores.get(parent_hash, 0), parent_score
                    )
            current = folio[parent_hash]

    for parent_hash, pscore in ancestor_scores.items():
        parent_class = folio[parent_hash]
        if parent_class:
            scored.append((parent_hash, parent_class, round(pscore, 1)))

    # Sort by score descending
    scored.sort(key=lambda x: x[2], reverse=True)

    # Phase 3: Build results with branch filtering
    results: list[dict] = []
    seen_hashes: set[str] = set()

    for iri_hash, owl_class, score in scored:
        if iri_hash in seen_hashes:
            continue
        seen_hashes.add(iri_hash)

        # Determine branch
        branch_name = ""
        if get_branch_fn:
            branch_name = get_branch_fn(folio, iri_hash)
        if branch_name in EXCLUDED_BRANCHES:
            continue
        if branch and branch_name and branch.lower() not in branch_name.lower():
            # Branch filter active and doesn't match — still include but lower priority
            pass

        results.append({
            "label": owl_class.label or iri_hash,
            "iri": owl_class.iri,
            "iri_hash": iri_hash,
            "definition": owl_class.definition,
            "synonyms": owl_class.alternative_labels or [],
            "branch": branch_name,
            "branch_color": get_branch_color(branch_name) if branch_name else "",
            "score": score,
        })

        if len(results) >= top_n:
            break

    return results
