# Brainstorm: One-Click Demo Exemplars

**Date**: 2026-03-16
**Status**: Ready for planning

## What We're Building

A "Demo" button in the header toolbar that, with a single click, opens ~10 browser tabs — each pre-populated with a fully enriched exemplar document. No pipeline run, no backend needed. Each tab loads instantly from pre-computed static JSON files.

### Exemplar Catalog (~10 documents)

**Substantive Law:**
- Litigation (e.g., motion to dismiss, complaint)
- Transactional (e.g., contract clause, merger agreement)
- Advisory (e.g., legal memo)
- Regulatory (e.g., compliance filing)

**Timekeeping:**
- Timekeeping Narratives (billing entries)

**Feature Showcases:**
- Multi-Branch (document rich in concepts that branch across multiple FOLIO paths)
- Individuals (document dense with citations, parties, entities)
- Property Verbs (document highlighting OWL ObjectProperty extraction)
- Synonyms (document with varied terminology mapping to same concepts)
- Kitchen Sink (a long, feature-rich document that exercises everything)

## Why This Approach

**Approach: URL-param hydration with static JSON files**

- "Demo" button calls `window.open('index.html?demo=<name>')` for each exemplar
- Frontend detects `?demo=X` on page load, fetches `frontend/demos/X.json`
- JSON contains the full job result (annotations, individuals, properties, triples, metadata) plus source text
- Frontend hydrates the UI exactly as if the pipeline had just completed
- Each tab is fully self-contained and independent

**Why this over alternatives:**
- **Simplest** — no IndexedDB, no backend endpoints, no sessionStorage coordination
- **Works offline** — static files, no API calls needed
- **Instant** — no pipeline execution, no loading spinners
- **Debuggable** — JSON files are human-readable, easy to inspect and update

## Key Decisions

1. **Pre-computed results** — exemplar JSON files are generated once via CLI script, committed to repo
2. **Static JSON in `frontend/demos/`** — served alongside index.html, no backend dependency
3. **One click = all tabs** — Demo button opens all ~10 exemplars simultaneously
4. **New curated documents** — purpose-built texts designed to showcase specific features (not reusing existing SAMPLES)
5. **CLI generation script** — Python script runs each exemplar through the pipeline, saves job result JSON to `frontend/demos/`
6. **URL parameter `?demo=X`** — frontend routing mechanism to load exemplar data

## Resolved Questions

1. **Tab title differentiation** — Yes, each demo tab gets a distinct title (e.g., "FOLIO Enrich — Demo: Litigation")
2. **Demo button placement** — Next to the "New" button in the header toolbar
3. **Interactivity** — Fully interactive with a "Reset Demo" button to restore original pre-computed state
4. **Pop-up blocker handling** — Try `window.open()` for all tabs; if blocked, show fallback modal with clickable links
