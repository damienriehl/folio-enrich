---
title: "fix: Reduce false positives with coverage-ratio, multi-word POS, NER cross-validation, and word-count gates"
type: fix
status: completed
date: 2026-03-15
---

# Fix: Reduce False Positives with 4 Precision Improvements

## Overview

Two categories of false positives degrade classification precision:

1. **Substring over-matching**: "Amended Complaint" scores 85/100 against "Motion to File Amended Complaint" because substring matching treats query-in-label the same regardless of coverage ratio.
2. **Semantic type mismatch**: "Limitation Period" classified as "Organization" at 78% confidence because POS/NER validation skips multi-word spans entirely.

Four targeted fixes address these without reducing recall — all are soft confidence penalties, not hard gates.

## Problem Statement

### Bug 1: Substring Over-Matching

In `search.py:164`, when the query is a substring of a candidate label, the score is a flat 85.0:

```python
if len(query_lower) >= 4 and query_lower in label_lower:
    label_score = 85.0
```

"amended complaint" (17 chars) inside "motion to file amended complaint" (31 chars) = 85.0 — only 7 points below an exact 2-word match (92.0). The system cannot distinguish "partial coverage of a longer concept" from "near-exact match."

### Bug 2: Semantic Type Mismatch

`reconciliation_stage.py:168` skips all multi-word spans:

```python
if " " in span_text.strip():
    continue
```

This means "Limitation Period" (2 words) receives zero POS validation. Combined with no NER cross-checking, the pipeline accepts the LLM's misclassification without any semantic sanity check.

## Proposed Solution

### Fix 1: Coverage-Ratio Penalty for Substring Matches

**File**: `backend/app/services/folio/search.py` — `_compute_relevance_score()`

Scale substring match scores by the character coverage ratio:

```python
# Line 164: query-in-label
if len(query_lower) >= 4 and query_lower in label_lower:
    coverage = len(query_lower) / len(label_lower)
    label_score = 85.0 * coverage
    # "amended complaint" / "motion to file amended complaint" = 17/31 = 0.55 → score 46.5
    # vs exact match "amended complaint" = 92.0

# Line 182: query-in-preferred-label (same pattern)
if len(query_lower) >= 4 and query_lower in pref_lower:
    coverage = len(query_lower) / len(pref_lower)
    pref_score = 84.0 * coverage
```

**Score impact examples**:

| Query | Label | Coverage | Old Score | New Score |
|---|---|---|---|---|
| "amended complaint" | "motion to file amended complaint" | 0.55 | 85 | 46.5 |
| "amended complaint" | "amended complaint" | 1.0 (exact) | 92 | 92 (unchanged) |
| "contract" | "contract law" | 0.62 | 85 | 52.5 |
| "breach of contract" | "breach of contract claim" | 0.75 | 85 | 63.8 |

**Leave unchanged**: The reverse case (`label_lower in query_lower`, line 166) already has a 0.3 ratio guard and scores 78.0.

### Fix 2: Extend POS Adjustments to Multi-Word Spans

**File**: `backend/app/pipeline/stages/reconciliation_stage.py` — `_apply_pos_adjustments()`
**File**: `backend/app/pipeline/stages/property_stage.py` — `_apply_pos_adjustments()`

Remove the multi-word skip and use `get_majority_pos()` for all spans. For 2-word ties, use priority-based resolution:

```python
# For class concepts: if ANY token is NOUN/PROPN, treat as noun-like (boost candidate)
# For class concepts: if MAJORITY is VERB/ADV and match_type == "alternative", penalize
# For property concepts: if ANY token is VERB/AUX, treat as verb-like (boost candidate)

# Implementation approach:
pos_tags = get_pos_for_span(ann.span.start, ann.span.end, sentence_pos)
if not pos_tags:
    continue

# For class concepts — check for noun-like presence
has_noun = any(p in ("NOUN", "PROPN") for p in pos_tags)
has_adj = any(p == "ADJ" for p in pos_tags)
majority = Counter(pos_tags).most_common(1)[0][0]

if has_noun:
    # Boost: noun-like span matches class concept
    boost = boost_base * _POS_CONCEPT_BOOST_MULTIPLIERS.get("NOUN", 1.0)
    concept.confidence = min(1.0, concept.confidence + boost)
elif has_adj and not any(p in ("VERB", "ADV") for p in pos_tags):
    # ADJ-only (no verbs) — mild boost
    boost = boost_base * _POS_CONCEPT_BOOST_MULTIPLIERS.get("ADJ", 0.6)
    concept.confidence = min(1.0, concept.confidence + boost)
elif majority in ("VERB", "ADV") and concept.match_type == "alternative":
    # Penalty: verb-like span mismatches class concept
    concept.confidence = max(0.0, concept.confidence - penalty)
```

**Tie-breaking rationale**: For short spans, "any NOUN present" is more reliable than majority vote. "Limitation Period" (NOUN, NOUN) → clear boost. "Amended Complaint" (ADJ, NOUN) → has NOUN → boost. "Running Quickly" (VERB, ADV) → no noun → penalty.

### Fix 3: spaCy NER Cross-Validation

**Phase A — NER Extraction** (piggyback on existing spaCy parse)

**File**: `backend/app/pipeline/stages/triple_stage.py` — `EarlyTripleStage`

EarlyTripleStage already runs `get_spacy_nlp()` on the full text. Extend it to also extract NER entities:

```python
# After existing sentence_pos extraction
ner_entities = []
for ent in doc.ents:
    ner_entities.append({
        "text": ent.text,
        "start": ent.start_char,
        "end": ent.end_char,
        "label": ent.label_,
    })
job.result.metadata["spacy_ner_entities"] = ner_entities
```

This adds ~0ms since the NER model already ran — we're just reading `doc.ents`.

**Phase B — NER-Branch Mapping**

**File**: `backend/app/pipeline/stages/reconciliation_stage.py` — new `_apply_ner_adjustments()`

Define NER-to-branch affinity mapping:

```python
_NER_BRANCH_AFFINITY: dict[str, set[str]] = {
    "ORG": {"Actor / Player", "Legal Entity", "Governmental Body", "Industry"},
    "PERSON": {"Actor / Player"},
    "GPE": {"Location", "Governmental Body"},
    "LOC": {"Location"},
    "DATE": {"Event", "Status"},
    "MONEY": {"Currency", "Financial Concepts and Metrics", "Asset Type"},
    "LAW": {"Legal Authorities"},
    "NORP": {"Actor / Player"},
    "FAC": {"Location", "Forums and Venues"},
}
```

**Penalty logic** (contradiction only — conservative):

```python
def _apply_ner_adjustments(self, job: Job) -> tuple[int, int]:
    ner_entities = job.result.metadata.get("spacy_ner_entities", [])
    if not ner_entities:
        return 0, 0

    boosted = penalized = 0
    for ann in job.result.annotations:
        if ann.state == "rejected" or not ann.concepts:
            continue
        concept = ann.concepts[0]
        branch = concept.branch or ""

        # Find overlapping NER entity
        ner_label = _find_overlapping_ner(ann.span.start, ann.span.end, ner_entities)
        if ner_label is None:
            continue  # No NER signal — do nothing (safe default)

        compatible_branches = _NER_BRANCH_AFFINITY.get(ner_label, set())
        if not compatible_branches:
            continue  # Unmapped NER label — do nothing

        if branch in compatible_branches:
            # NER confirms branch — small boost
            concept.confidence = min(1.0, concept.confidence + settings.ner_agreement_boost)
            boosted += 1
        else:
            # NER contradicts branch — penalty
            concept.confidence = max(0.0, concept.confidence - settings.ner_contradiction_penalty)
            penalized += 1
            if concept.confidence < 0.20:
                ann.state = "rejected"
```

**Key design decisions**:
- **No penalty for "no NER"** — too risky for recall. "Court" (no NER) under Governmental Body is valid. Only penalize when NER *actively contradicts* the branch.
- **Overlap matching**: any overlap between annotation span and NER span counts as a match.
- **Conservative penalties**: default 0.08 contradiction, 0.04 agreement boost.

### Fix 4: Word-Count Ratio Gate

**File**: `backend/app/services/folio/search.py` — `_compute_relevance_score()`

After Fix 1's coverage-ratio scaling, apply a second penalty based on content-word ratio:

```python
# After the coverage-ratio scaling from Fix 1:
if len(query_lower) >= 4 and query_lower in label_lower:
    coverage = len(query_lower) / len(label_lower)
    label_score = 85.0 * coverage  # Fix 1

    # Fix 4: word-count ratio gate
    query_words = len(query_content)
    label_words = len(label_content)
    if label_words > 0:
        word_ratio = query_words / label_words
        if word_ratio < 0.5:
            label_score *= word_ratio / 0.5  # Additional scaling below threshold
            # Example: 2/5 = 0.4, penalty = 0.4/0.5 = 0.8x multiplier
```

**Composition of Fixes 1+4** (sequential — Fix 1 first, then Fix 4 on the reduced score):

| Query | Label | Fix 1 (char ratio) | Fix 4 (word ratio) | Combined Score |
|---|---|---|---|---|
| "amended complaint" (2w) | "motion to file amended complaint" (5w) | 85 × 0.55 = 46.5 | × 0.8 (2/5=0.4) | 37.2 |
| "contract" (1w) | "contract law" (2w) | 85 × 0.62 = 52.5 | × 1.0 (1/2=0.5, at threshold) | 52.5 |
| "breach of contract" (3w) | "breach of contract claim" (4w) | 85 × 0.75 = 63.8 | × 1.0 (3/4=0.75, above threshold) | 63.8 |

**The exact match path (line 151) is unaffected** — it returns early before any substring logic.

## Technical Considerations

### Interaction Between Fixes

- **Fixes 1+4** operate in `_compute_relevance_score()` (search scoring). They compound but are bounded — the minimum combined score for a substring match is ~15-20, well above 0.
- **Fix 2** operates in reconciliation (post-search). It adjusts confidence on already-resolved annotations. Independent of Fixes 1+4.
- **Fix 3** operates in reconciliation alongside Fix 2. They are additive — a span can receive both POS and NER adjustments.
- **Metadata sync**: Fixes 2+3 must call `_sync_pos_to_metadata()` (or a new `_sync_ner_to_metadata()`) to propagate adjustments downstream to Resolution → StringMatch.

### Performance

- **Fixes 1+4**: Zero overhead — simple arithmetic in existing code path.
- **Fix 2**: Marginal — `get_majority_pos()` already exists, just called for more spans.
- **Fix 3**: ~0ms for NER extraction (piggybacks on existing spaCy parse). O(n×m) for NER-annotation overlap check where n=annotations, m=NER entities. For a typical document (~50 annotations, ~20 NER entities), this is <1ms.

### Configuration

New settings in `backend/app/config.py`:

```python
# Search precision gates (Fixes 1+4)
search_coverage_penalty_enabled: bool = True
search_word_ratio_penalty_enabled: bool = True
search_word_ratio_threshold: float = 0.5

# NER cross-validation (Fix 3)
ner_cross_validation_enabled: bool = True
ner_contradiction_penalty: float = 0.08
ner_agreement_boost: float = 0.04
```

Fix 2 uses existing `pos_confidence_enabled` master switch — no new flag needed.

## Acceptance Criteria

### Functional

- [x] "Amended Complaint" no longer matches "Motion to File Amended Complaint" as top candidate (exact match wins decisively)
- [x] "Limitation Period" no longer classified as "Organization" (POS check detects NOUN ≠ entity-branch expectation)
- [x] Multi-word spans receive POS-based confidence adjustments (boost for noun-like → class, penalty for verb-like → class)
- [x] spaCy NER entities are extracted and stored in job metadata during EarlyTripleStage
- [x] NER-branch contradictions reduce confidence; NER-branch agreements boost confidence
- [x] All 4 fixes are independently toggleable via config settings
- [x] All 600+ existing tests pass

### Non-Functional

- [x] No measurable latency increase (all fixes are O(1) or piggyback on existing computation)
- [x] Lineage events recorded for all confidence adjustments (POS multi-word, NER boost/penalty)

## Implementation Phases

### Phase 1: Search Scoring (Fixes 1+4)

**Files modified**:
- `backend/app/services/folio/search.py` — `_compute_relevance_score()`
- `backend/app/config.py` — new settings
- `backend/tests/test_search.py` — new test cases

**Tasks**:
1. Add coverage-ratio scaling to query-in-label branch (line 164)
2. Add coverage-ratio scaling to query-in-preferred-label branch (line 182)
3. Add word-count ratio gate after coverage scaling
4. Add config settings for enable/disable and threshold
5. Write regression tests for both false positive examples
6. Write golden-path tests verifying true positive scores don't drop below thresholds
7. Run full test suite

### Phase 2: Multi-Word POS (Fix 2)

**Files modified**:
- `backend/app/pipeline/stages/reconciliation_stage.py` — `_apply_pos_adjustments()`
- `backend/app/pipeline/stages/property_stage.py` — `_apply_pos_adjustments()`
- `backend/tests/test_pos_confidence.py` — update skip-multiword tests

**Tasks**:
1. Replace multi-word skip with `get_pos_for_span()` + priority-based resolution
2. Apply noun-presence boost for class concepts, verb-presence boost for properties
3. Maintain `match_type == "alternative"` guard for penalties (backward compat)
4. Update tests that assert multi-word spans are skipped → now assert they are adjusted
5. Add new tests for tie-breaking (ADJ+NOUN, VERB+NOUN scenarios)
6. Verify `_sync_pos_to_metadata()` propagates multi-word adjustments
7. Run full test suite

### Phase 3: NER Cross-Validation (Fix 3)

**Files modified**:
- `backend/app/pipeline/stages/triple_stage.py` — NER extraction in EarlyTripleStage
- `backend/app/pipeline/stages/reconciliation_stage.py` — new `_apply_ner_adjustments()`
- `backend/app/config.py` — NER settings
- `backend/tests/test_pos_confidence.py` (or new test file) — NER tests

**Tasks**:
1. Extract NER entities from existing spaCy doc in EarlyTripleStage
2. Store as `metadata["spacy_ner_entities"]` list of dicts
3. Implement `_apply_ner_adjustments()` with overlap-based span matching
4. Define `_NER_BRANCH_AFFINITY` mapping
5. Wire into reconciliation flow after POS adjustments
6. Add metadata sync for NER-adjusted confidence
7. Add config settings with sensible defaults
8. Write tests for NER agreement boost, NER contradiction penalty, no-NER-no-penalty
9. Run full test suite

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Fix 1+4 over-penalizes legitimate partial matches like "Contract" → "Contract Law" | Low | Medium | Coverage ratio for "contract"/"contract law" = 0.62, yielding score 52.5 — still well above 30.0 threshold. Word ratio = 0.5 → no additional penalty. |
| Fix 2 gives wrong POS for legal jargon | Medium | Low | Priority-based resolution (any NOUN = noun-like) is more robust than majority vote. Legal text is noun-heavy. |
| Fix 3 NER misclassifies legal terms | Medium | Low | Conservative: only penalize contradictions, not absence. spaCy NER stop-phrase pattern already established. |
| Compound penalties across all 4 fixes push valid concepts below thresholds | Low | Medium | Each fix is independently toggleable. Default penalties are small (0.04-0.10). Monitor via lineage events. |

## Sources & References

### Internal
- `backend/app/services/folio/search.py:164` — substring scoring
- `backend/app/pipeline/stages/reconciliation_stage.py:168` — multi-word POS skip
- `backend/app/pipeline/stages/branch_judge_stage.py:97-118` — POS-branch affinity pattern
- `backend/app/services/individual/entity_extractors.py:426-470` — NER stop-phrase pattern
- `backend/app/services/nlp/pos_lookup.py` — POS lookup utilities
- `docs/plans/2026-03-15-001-feat-pos-confidence-boost-classification-plan.md` — related POS feature plan
