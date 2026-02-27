# FOLIO Enrich

**Tag every legal document with precise, machine-readable legal concepts, individuals, and relationships — automatically.**

Legal documents contain thousands of concepts buried in dense prose: causes of action, contract terms, regulatory frameworks, named entities, and inter-concept relationships. FOLIO Enrich reads your documents, identifies those concepts, maps each one to the [FOLIO ontology](https://github.com/FOLIO-Ontology/FOLIO) (18,000+ standardized legal concepts), extracts named individuals (citations, parties, dates, amounts) and OWL object properties (legal verbs and relationships), scores confidence, and exports structured results in 13 formats — all through a single API call.

Upload complaints, contracts, or regulatory filings.

Seconds later, receive a structured annotation layer that machines can search, filter, sort, and analyze.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Pipeline Stages](#pipeline-stages)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Export Formats](#export-formats)
- [Frontend](#frontend)
- [LLM Integration](#llm-integration)
- [Embedding & Semantic Search](#embedding--semantic-search)
- [Confidence Scoring](#confidence-scoring)
- [Individual Extraction](#individual-extraction)
- [Property Extraction](#property-extraction)
- [Metadata Extraction](#metadata-extraction)
- [Document Type Detection](#document-type-detection)
- [Synthetic Document Generation](#synthetic-document-generation)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Dependencies](#dependencies)
- [License](#license)

---

## Features

- **Multi-format ingestion** — PDF, DOCX, HTML, Markdown, RTF, email (EML/MSG), and plain text
- **Dual-path enrichment** — spaCy EntityRuler and LLM concept extraction run in parallel, then reconcile
- **FOLIO ontology mapping** — resolves every annotation to a FOLIO IRI with multi-candidate backup lists
- **Multi-branch classification** — assigns multiple FOLIO branch categories per concept with nested same-type span support
- **Individual extraction** — three-path hybrid (eyecite/citeurl citations, 14 regex/spaCy extractors, LLM class linking) for OWL individuals
- **Property extraction** — Aho-Corasick + LLM identification of OWL ObjectProperties (legal verbs and relationships) with domain/range/inverse linking
- **28-field metadata extraction** — pipeline-aware context engineering extracts parties, dates, courts, claims, attorneys, and more
- **Document type detection** — early parallel LLM classification with post-pipeline quality cross-check
- **Calibrated confidence scoring** — graduated initial scores, contextual LLM reranking, branch judge blending, and embedding triage across 5 stages
- **Containment-aware dedup** — nested spans (A inside B) survive across all stages; partial overlaps resolve to longer match
- **13 export formats** — JSON, JSON-LD, XML, CSV, JSONL, Parquet, Elasticsearch bulk, Neo4j CSV, RAG chunks, RDF/Turtle, brat standoff, HTML, Excel
- **Real-time streaming** — Server-Sent Events (SSE) for live pipeline progress including individuals, properties, and document type
- **Annotation lifecycle** — promote, reject, restore, cascade-promote, and bulk-reject operations with full lineage tracking
- **Per-task LLM routing** — assign different LLM providers to 9 pipeline tasks (classifier, extractor, concept, branch judge, area of law, synthetic, individual, property, document type)
- **14 LLM providers** — OpenAI, Anthropic, Google Gemini, Mistral, Cohere, Meta Llama, Groq, xAI, GitHub Models, Ollama, LM Studio, Llamafile, and custom OpenAI-compatible endpoints
- **Semantic search** — FAISS-backed embedding index for fast concept lookup and conflict resolution
- **Synthetic document generation** — LLM-powered generation of realistic legal test documents across 40+ document types
- **Legal citation parsing** — eyecite + citeurl integration for citation extraction and URL resolution
- **Feedback system** — per-annotation user feedback with aggregated insights dashboard
- **Dark-themed UI** — single-file browser frontend with concept graph visualization (Cytoscape), individual/property tabs, multi-branch overlays, and polyhierarchy tree views

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Frontend (index.html)                    │
│        Vanilla JS · Dark theme · Cytoscape graph viz             │
│   Tabs: Annotated Text · Concepts · Individuals · Properties    │
│         Triples · Metadata · Export · Insights                   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ REST + SSE
┌──────────────────────────▼───────────────────────────────────────┐
│                      FastAPI Backend                              │
│  Middleware: Rate Limit → Security → CORS → Error Handler        │
├──────────────────────────────────────────────────────────────────┤
│  Routes: /enrich  /export  /concepts  /synthetic  /feedback      │
│          /settings  /health                                      │
├──────────────────────────────────────────────────────────────────┤
│                    Pipeline Orchestrator                          │
│                                                                  │
│  Phase 1 (Sequential)       Phase 2 (Parallel)                   │
│  ┌─────────────────┐   ┌─────────────────────────────┐           │
│  │ 1. Ingestion    │   │ 3. EntityRuler         ─┐   │           │
│  │ 2. Normalize    │──▶│ 4. LLM Concept         ─┤   │           │
│  └─────────────────┘   │ 5. EarlyIndividual     ─┤   │           │
│                         │ 6. EarlyProperty       ─┤   │           │
│                         │ 7. DocumentType        ─┘   │           │
│                         └──────────────┬──────────────┘           │
│                                        │                          │
│  Phase 3 (Sequential)                  ▼                          │
│  ┌──────────────────────────────────────────────────┐             │
│  │  8. Reconciliation   12. LLMIndividual           │             │
│  │  9. Resolution       13. LLMProperty             │             │
│  │ 10. Rerank           14. Dependency              │             │
│  │ 11. BranchJudge      15. StringMatch             │             │
│  │                      16. Metadata                │             │
│  └──────────────────────────────────────────────────┘             │
│                                                                  │
│  Post-pipeline: Area of Law · Document Type Quality Check        │
├──────────────────────────────────────────────────────────────────┤
│  Services: FOLIO · Embedding · LLM Registry · Individual ·       │
│            Property · Quality · Job Store                         │
├──────────────────────────────────────────────────────────────────┤
│  Storage: ~/.folio-enrich/jobs/ (JSON, atomic writes)            │
└──────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Stages

The pipeline runs in three phases with 5 parallel stages and 9 sequential post-parallel stages. LLM-dependent stages are automatically skipped when no LLM is configured.

| # | Stage | Phase | Description |
|---|-------|-------|-------------|
| 1 | **Ingestion** | Pre-parallel | Converts PDF, DOCX, HTML, Markdown, RTF, email, or plain text to raw text |
| 2 | **Normalization** | Pre-parallel | Chunks text into semantic chunks, builds sentence index |
| 3 | **EntityRuler** | Parallel | spaCy pattern matching against FOLIO preferred and alternative labels |
| 4 | **LLM Concept** | Parallel | LLM-based concept extraction per chunk (runs concurrently with EntityRuler) |
| 5 | **EarlyIndividual** | Parallel | Citation parsing (eyecite/citeurl) + 14 regex/spaCy entity extractors |
| 6 | **EarlyProperty** | Parallel | Aho-Corasick automaton matching FOLIO ObjectProperty labels |
| 7 | **DocumentType** | Parallel | LLM identifies what the document "calls itself" from title/header |
| 8 | **Reconciliation** | Post-parallel | Merges EntityRuler + LLM results using embedding-powered triage |
| 9 | **Resolution** | Post-parallel | Resolves concept text to FOLIO IRIs with multi-candidate backup lists |
| 10 | **Contextual Rerank** | Post-parallel | LLM reranking using full document context (50/50 blend with pipeline score) |
| 11 | **Branch Judge** | Post-parallel | LLM assigns FOLIO branch categories for ambiguous concepts (70/30 blend) |
| 12 | **String Match** | Post-parallel | Aho-Corasick matching with containment-aware dedup and multi-branch keying |
| 13 | **LLM Individual** | Post-parallel | LLM links individuals to resolved OWL class annotations |
| 14 | **LLM Property** | Post-parallel | LLM identifies properties with domain/range cross-linking |
| 15 | **Dependency** | Post-parallel | spaCy dependency parsing to extract subject-predicate-object triples |
| 16 | **Metadata** | Post-parallel | LLM extracts 28 metadata fields using full pipeline context |

**Post-pipeline**: Area of Law assessment classifies legal domains. Document Type quality cross-check validates findings against pipeline output.

---

## Quick Start

### Prerequisites

- Python 3.11+
- A spaCy English model (`en_core_web_sm`)

### Installation

```bash
# Clone the repository
git clone https://github.com/damienriehl/folio-enrich.git
cd folio-enrich/backend

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Download spaCy model
python -m spacy download en_core_web_sm
```

### Running the Server

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8731 --reload
```

The API is now available at `http://localhost:8731`. Open `frontend/index.html` in a browser for the UI.

### Basic Usage

```bash
# Submit a document for enrichment
curl -X POST http://localhost:8731/enrich \
  -H "Content-Type: application/json" \
  -d '{"text": "The plaintiff filed a motion for summary judgment in the District Court."}'

# Check job status (replace JOB_ID)
curl http://localhost:8731/enrich/JOB_ID

# Export results as JSON-LD
curl http://localhost:8731/enrich/JOB_ID/export?format=jsonld

# Stream pipeline progress via SSE
curl http://localhost:8731/enrich/JOB_ID/stream
```

---

## Configuration

All settings use environment variables with the `FOLIO_ENRICH_` prefix. Managed via [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIO_ENRICH_JOBS_DIR` | `~/.folio-enrich/jobs` | Job storage directory |
| `FOLIO_ENRICH_MAX_UPLOAD_SIZE` | `52428800` (50 MB) | Maximum upload size in bytes |
| `FOLIO_ENRICH_MAX_CONCURRENT_JOBS` | `10` | Maximum concurrent pipeline jobs |
| `FOLIO_ENRICH_JOB_RETENTION_DAYS` | `30` | Days before jobs are auto-cleaned |

### LLM Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIO_ENRICH_LLM_PROVIDER` | `google` | Global default LLM provider |
| `FOLIO_ENRICH_LLM_MODEL` | `gemini-3-flash` | Global default model |
| `FOLIO_ENRICH_OPENAI_API_KEY` | — | OpenAI API key |
| `FOLIO_ENRICH_ANTHROPIC_API_KEY` | — | Anthropic API key |
| `FOLIO_ENRICH_GOOGLE_API_KEY` | — | Google Gemini API key |

#### Per-Task LLM Overrides

Each pipeline task can use a different provider/model:

| Variable Pattern | Example |
|-----------------|---------|
| `FOLIO_ENRICH_LLM_{TASK}_PROVIDER` | `FOLIO_ENRICH_LLM_CLASSIFIER_PROVIDER=anthropic` |
| `FOLIO_ENRICH_LLM_{TASK}_MODEL` | `FOLIO_ENRICH_LLM_CLASSIFIER_MODEL=claude-sonnet-4-6` |

Tasks: `CLASSIFIER`, `EXTRACTOR`, `CONCEPT`, `BRANCH_JUDGE`, `AREA_OF_LAW`, `SYNTHETIC`, `INDIVIDUAL`, `PROPERTY`, `DOCUMENT_TYPE`

### Individual & Property Extraction Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIO_ENRICH_INDIVIDUAL_EXTRACTION_ENABLED` | `true` | Enable individual (named entity) extraction |
| `FOLIO_ENRICH_INDIVIDUAL_REGEX_ONLY` | `false` | Skip LLM class linking, use only regex/spaCy |
| `FOLIO_ENRICH_PROPERTY_EXTRACTION_ENABLED` | `true` | Enable property (verb/relation) extraction |
| `FOLIO_ENRICH_PROPERTY_REGEX_ONLY` | `false` | Skip LLM property identification, use only Aho-Corasick |

### Embedding Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIO_ENRICH_EMBEDDING_PROVIDER` | `local` | Embedding provider (`local`, `ollama`, `openai`) |
| `FOLIO_ENRICH_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model name |
| `FOLIO_ENRICH_EMBEDDING_DISABLED` | `false` | Disable embedding features entirely |
| `FOLIO_ENRICH_SEMANTIC_SIMILARITY_THRESHOLD` | `0.80` | Minimum similarity for conflict resolution |

### Chunking Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIO_ENRICH_MAX_CHUNK_CHARS` | `3000` | Maximum characters per text chunk |
| `FOLIO_ENRICH_CHUNK_OVERLAP_CHARS` | `200` | Overlap between adjacent chunks |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIO_ENRICH_RATE_LIMIT_REQUESTS` | `60` | Max requests per window |
| `FOLIO_ENRICH_RATE_LIMIT_WINDOW` | `60` | Window size in seconds |

---

## API Reference

### Enrichment

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/enrich` | Submit a document for enrichment (returns `202` with `job_id`) |
| `GET` | `/enrich/{job_id}` | Get job status and results (includes annotations, individuals, properties) |
| `GET` | `/enrich/{job_id}/stream` | SSE stream of pipeline progress |
| `GET` | `/enrich/branches` | List all FOLIO branches with display colors |

### Annotation Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/enrich/{job_id}/annotations/{id}/promote` | Promote a backup concept to primary |
| `POST` | `/enrich/{job_id}/annotations/{id}/reject` | Dismiss an annotation as a false positive |
| `POST` | `/enrich/{job_id}/annotations/{id}/restore` | Restore a dismissed annotation |
| `POST` | `/enrich/{job_id}/cascade-promote` | Bulk promote a concept across all matching annotations |
| `POST` | `/enrich/{job_id}/annotations/bulk-reject` | Bulk reject all annotations with a given IRI |
| `GET` | `/enrich/{job_id}/annotations/{id}/lineage` | Full event history for an annotation |

### Export

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/enrich/{job_id}/export?format=json` | Export results in any of the 13 supported formats |

Query parameters: `format` (required), `include_dismissed` (default `false`)

All export formats include annotations, individuals, and properties sections.

### Concepts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/concepts/{iri_hash}` | Look up a FOLIO concept by IRI hash |
| `GET` | `/concepts/{iri_hash}/graph` | BFS entity graph around a concept |

### Synthetic Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/synthetic` | Generate a synthetic legal document |
| `GET` | `/synthetic/types` | List available document types (10 categories, 40+ types) |

### Feedback

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/feedback` | Submit feedback on an annotation |
| `GET` | `/feedback/insights` | Aggregated feedback insights |
| `GET` | `/feedback/insights/csv` | Export feedback data as CSV |

### Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/settings/llm/providers` | List available LLM providers |
| `GET` | `/settings/llm/models` | List models for a provider |
| `POST` | `/settings/llm/test` | Test an LLM connection |
| `GET` | `/settings/embedding/providers` | List embedding providers |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Simple health check |
| `GET` | `/health/detail` | Detailed subsystem health (FOLIO, embedding, LLM, spaCy) |

---

## Export Formats

### Tier 1 — Text-Based

| Format | Content-Type | Description |
|--------|-------------|-------------|
| `json` | `application/json` | Flat JSON with annotations, individuals, and properties arrays |
| `jsonld` | `application/ld+json` | JSON-LD with `@context` for Linked Data |
| `xml` | `application/xml` | Hierarchical XML with annotation elements |
| `csv` | `text/csv` | One row per annotation |
| `jsonl` | `application/x-ndjson` | Line-delimited JSON |

### Tier 2 — Specialized

| Format | Content-Type | Description |
|--------|-------------|-------------|
| `parquet` | `application/octet-stream` | Apache Parquet columnar format |
| `elasticsearch` | `application/x-ndjson` | Elasticsearch bulk indexing format |
| `neo4j` | `text/csv` | CSV formatted for Neo4j graph import |
| `rag` | `application/json` | RAG-optimized chunks with embedded annotations |
| `rdf` | `text/turtle` | RDF/Turtle for Semantic Web integration |
| `brat` | `text/plain` | brat standoff annotation format |
| `html` | `text/html` | Interactive HTML with styled tooltips and confidence bars |
| `excel` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Spreadsheet with color-coded confidence |

---

## Frontend

The frontend is a single-file SPA at `frontend/index.html` — no build step required.

**Capabilities:**
- Drag-and-drop document upload (or paste text directly)
- Real-time pipeline progress via SSE with progressive rendering
- Annotation viewer with ranked concept candidates and confidence bars
- Color-coded FOLIO branch badges (Actor, Area of Law, Document, Engagement, Event, Location, etc.)
- Multi-branch overlays with stacked gradient borders and colored dot indicators
- Polyhierarchy tree views for multi-parent concept hierarchies
- Individuals tab with citation details, entity cards, and OWL class links
- Properties tab with verb/relation cards showing definition, domain/range, and inverse
- Document type banner with confidence indicator
- "N sources agree" badges for multi-source annotation confirmation
- Annotation state management (preliminary / confirmed / rejected)
- Concept graph visualization using Cytoscape with Dagre layout
- Right detail panel with concept info, entity graph, and ancestry tree
- Cascade-promote and bulk-reject operations
- Export menu for all 13 formats
- LLM provider settings panel
- Dark theme

---

## LLM Integration

### Supported Providers

| Provider | Env Key Suffix | Default Model |
|----------|---------------|---------------|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| Google Gemini | `GOOGLE_API_KEY` | `gemini-3-flash-preview` |
| Mistral | `MISTRAL_API_KEY` | `mistral-medium-latest` |
| Cohere | `COHERE_API_KEY` | `command-a-03-2025` |
| Meta Llama | `META_API_KEY` | — |
| Groq | `GROQ_API_KEY` | — |
| xAI (Grok) | `XAI_API_KEY` | — |
| GitHub Models | `GITHUB_TOKEN` | — |
| Ollama | — (local) | — |
| LM Studio | — (local) | — |
| Llamafile | — (local) | — |
| Custom endpoint | `CUSTOM_API_KEY` | — |

### LLM Pipeline Tasks

Each task can be independently routed to a different provider:

| Task | Pipeline Role |
|------|--------------|
| **Classifier** | Document type classification |
| **Extractor** | Structured metadata field extraction (28 fields) |
| **Concept** | Legal concept identification from text chunks |
| **Branch Judge** | FOLIO branch category assignment for ambiguous concepts |
| **Area of Law** | Post-pipeline legal domain classification |
| **Individual** | OWL individual class linking |
| **Property** | OWL ObjectProperty identification with domain/range |
| **Document Type** | Early parallel document self-identification |
| **Synthetic** | Test document generation |

The pipeline degrades gracefully — LLM-dependent stages are skipped when no provider is available, and the EntityRuler + String Match + EarlyIndividual + EarlyProperty stages still produce useful results.

---

## Embedding & Semantic Search

At startup, FOLIO Enrich pre-computes embeddings for all FOLIO concept labels and builds a FAISS index for fast similarity search.

### Providers

| Provider | Model | Notes |
|----------|-------|-------|
| **Local** (default) | `all-MiniLM-L6-v2` | Runs on CPU, no external calls |
| **OpenAI** | `text-embedding-3-small` | Requires API key |
| **Ollama** | Configurable | Local inference server |

### Uses in the Pipeline

1. **Reconciliation** — resolves conflicts when EntityRuler and LLM disagree on a concept
2. **Semantic Ruler** — supplements pattern matching with embedding similarity
3. **Resolution** — helps find the best FOLIO IRI when exact label match fails
4. **Concept Lookup** — powers the `/concepts` API for semantic search

---

## Confidence Scoring

Annotations pass through a multi-stage confidence calibration system. Each stage blends its signal with the running score using explicit weights.

### Stage 1: EntityRuler Initial Scores

| Match Type | Base Score |
|-----------|-----------|
| Multi-word preferred label | 0.90 |
| Single-word preferred label | 0.72 |
| Multi-word alternative label | 0.65 |
| Single-word alternative label | 0.35 |

### Stage 2: Reconciliation

- If EntityRuler and LLM agree: takes the higher confidence
- If they disagree: embedding similarity breaks the tie
- LLM-only concepts enter at LLM-reported confidence

### Stage 3: Contextual Rerank (50/50 Blend)

An LLM evaluates each annotation against the full document context using a calibrated rubric:

```
new_confidence = pipeline_score * 0.5 + context_score * 0.5
```

Rubric anchors: `0.95` = unambiguous match, `0.70` = plausible, `0.40` = weak, `0.20` = likely false positive

### Stage 4: Branch Judge (70/30 Blend)

An LLM assigns the correct FOLIO branch category:

```
new_confidence = existing_confidence * 0.7 + judge_score * 0.3
```

### Stage 5: Metadata Promotion

High-confidence annotations are promoted to document-level metadata fields.

---

## Individual Extraction

FOLIO Enrich extracts OWL individuals (named instances) using a three-path hybrid approach across two pipeline stages.

### EarlyIndividualStage (Parallel, No LLM)

- **Legal citations** — eyecite parses U.S. legal citations; citeurl normalizes forms and resolves URLs
- **14 regex/spaCy extractors** — dates, monetary amounts, addresses, durations, percentages, phone numbers, emails, URLs, statutory references, court names, case numbers, organization entities, person entities, and geopolitical entities

### LLMIndividualStage (Post-Parallel)

- **Class linking** — LLM links extracted individuals to resolved OWL class annotations with confidence scores and relationship types
- **Deduplication** — merges duplicates across extraction paths

### Individual Types

| Source | Extracted Types |
|--------|----------------|
| **eyecite + citeurl** | Case citations, statutory citations, regulatory citations with normalized forms and URLs |
| **Regex/spaCy** | DATE, MONEY, DURATION, PERCENT, ADDRESS, PHONE, EMAIL, URL, STATUTE, COURT, CASE_NUMBER, ORG, PERSON, GPE |
| **LLM** | Class-linked individuals with relationship to OWL class annotations |

---

## Property Extraction

FOLIO Enrich identifies OWL ObjectProperties (legal verbs and relationships) using a two-stage approach.

### EarlyPropertyStage (Parallel, No LLM)

- **Aho-Corasick automaton** — fast multi-pattern matching against all FOLIO ObjectProperty labels
- **Containment-aware overlap resolution** — contained spans survive, partial overlaps resolve to longer match

### LLMPropertyStage (Post-Parallel)

- **Contextual identification** — LLM identifies property verbs in context with domain/range cross-linking
- **Merge and dedup** — combines with early results, deduplicates

### Property Data

Each extracted property includes:
- **FOLIO IRI** — resolved ObjectProperty identifier
- **Label and definition** — from FOLIO ontology
- **Domain and range** — OWL class constraints
- **Inverse relation** — linked inverse property (if any)
- **Alternative labels and examples** — from SKOS metadata
- **Confidence score** — extraction confidence

---

## Metadata Extraction

The Metadata stage runs last in the pipeline and uses all prior pipeline output as structured context for LLM extraction.

### 28 Extracted Fields

| Category | Fields |
|----------|--------|
| **Case identification** | `case_name`, `case_number`, `docket_entry_number`, `court`, `jurisdiction` |
| **Parties and people** | `parties` (with roles), `judge`, `attorneys` (with affiliations), `signatories`, `witnesses`, `author`, `recipient` |
| **Legal substance** | `cause_of_action`, `claim_types`, `relief_sought`, `disposition`, `standard_of_review`, `governing_law`, `procedural_posture` |
| **Dates** | `date_filed`, `date_signed`, `date_effective`, `date_due`, `dates_mentioned` |
| **Document info** | `document_title`, `related_documents`, `confidentiality`, `contract_type` |

Additional context-aware fields: `counterparties`, `term_duration`, `termination_conditions`, `consideration`, `addresses`, `has_exhibits`, `exhibit_list`, `language`

### Pipeline Context Used

The LLM receives structured context from all upstream stages:
- Individuals grouped by type (citations, persons, organizations, dates, amounts)
- Low-confidence entities with surrounding sentence context
- Extracted properties with FOLIO labels
- Resolved concepts with branch classifications
- Subject-predicate-object triples from dependency parsing
- Areas of law assessment

---

## Document Type Detection

### DocumentTypeStage (Parallel)

Asks the LLM what the document "calls itself" from the title, caption, or header. Stores `self_identified_type` in metadata for use by all downstream stages.

### Post-Pipeline Quality Check

After pipeline completion, a DocumentTypeChecker cross-validates:
- Compares document type against discovered branches, concepts, and annotation counts
- Detects missing expected branches or unexpected dominant branches
- Stores `quality_signals` array with severity levels in metadata

---

## Synthetic Document Generation

Generate realistic legal documents for testing and demonstration.

### Document Categories

| Category | Example Types |
|----------|--------------|
| **Litigation** | Complaint, Motion for Summary Judgment, Appellate Brief, Discovery Request, Settlement Agreement, Court Order |
| **Contracts** | Employment Agreement, NDA, SaaS Agreement, License Agreement, Lease Agreement |
| **Corporate** | Articles of Incorporation, Board Resolution, Merger Agreement, Operating Agreement |
| **Regulatory** | SEC Filing, Agency Comment Letter, Compliance Policy |
| **Law Firm Operations** | Engagement Letter, Legal Opinion |
| **Real Estate** | Purchase Agreement, Deed of Trust, Easement Agreement |
| **Intellectual Property** | Patent Application, Trademark Registration |
| **Estate Planning** | Last Will and Testament, Trust Agreement |
| **Immigration** | Visa Petition, Naturalization Application |

### Usage

```bash
# List available document types
curl http://localhost:8731/synthetic/types

# Generate a document
curl -X POST http://localhost:8731/synthetic \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "complaint", "length": "medium", "jurisdiction": "California"}'
```

---

## Testing

```bash
cd backend
.venv/bin/python -m pytest tests/ -v
```

**586 tests** across 45 test files covering:

| Area | Tests Cover |
|------|------------|
| **Pipeline** | End-to-end pipeline, progressive pipeline, parallel execution, task LLM routing |
| **Stages** | EntityRuler, reconciliation, resolution, rerank, branch judge, annotation states |
| **Individuals** | Citation extraction, entity extraction, class linking, deduplication |
| **Properties** | Aho-Corasick matching, property dedup, domain/range resolution |
| **Document type** | Self-identification, quality cross-check signals |
| **Metadata** | 28-field extraction, pipeline context building |
| **Ingestion** | PDF, HTML, RTF, email, DOCX, Markdown, plain text |
| **LLM** | Provider registry, per-task routing, connection testing, pricing |
| **Embedding** | Semantic ruler, embedding index, FAISS index |
| **Export** | All Tier 1 formats, all Tier 2 formats |
| **Concepts** | Concept identification, concept detail, resolver |
| **Matching** | Aho-Corasick automaton, containment-aware dedup, multi-branch keying |
| **Feedback** | Submission, insights aggregation, dismiss/restore |
| **Infrastructure** | Security middleware, SSE streaming, job retention, rate limiting |

---

## Project Structure

```
folio-enrich/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app, startup, middleware
│   │   ├── config.py                        # Pydantic settings (env vars)
│   │   ├── api/routes/
│   │   │   ├── enrich.py                    # Document enrichment endpoints
│   │   │   ├── export.py                    # Export endpoints (13 formats)
│   │   │   ├── concepts.py                  # FOLIO concept lookup + graph
│   │   │   ├── synthetic.py                 # Synthetic document generation
│   │   │   ├── feedback.py                  # User feedback + insights
│   │   │   ├── settings.py                  # LLM/embedding configuration
│   │   │   └── health.py                    # Health checks
│   │   ├── models/
│   │   │   ├── annotation.py                # Annotation, Individual, PropertyAnnotation
│   │   │   ├── job.py                       # Job, JobStatus, JobResult
│   │   │   ├── document.py                  # Document formats and chunks
│   │   │   ├── llm_models.py                # LLM provider types (14)
│   │   │   └── embedding_models.py          # Embedding model config
│   │   ├── pipeline/
│   │   │   ├── orchestrator.py              # Three-phase parallel orchestrator
│   │   │   └── stages/
│   │   │       ├── base.py                  # PipelineStage ABC
│   │   │       ├── ingestion_stage.py       # Multi-format document ingestion
│   │   │       ├── normalization_stage.py   # Chunking + sentence indexing
│   │   │       ├── entity_ruler_stage.py    # spaCy pattern matching
│   │   │       ├── llm_concept_stage.py     # LLM concept extraction
│   │   │       ├── individual_stage.py      # EarlyIndividual + LLMIndividual
│   │   │       ├── property_stage.py        # EarlyProperty + LLMProperty
│   │   │       ├── document_type_stage.py   # Early document type classification
│   │   │       ├── reconciliation_stage.py  # Dual-path merge
│   │   │       ├── resolution_stage.py      # FOLIO IRI resolution
│   │   │       ├── rerank_stage.py          # Contextual LLM reranking
│   │   │       ├── branch_judge_stage.py    # Branch category assignment
│   │   │       ├── string_match_stage.py    # Aho-Corasick matching
│   │   │       ├── metadata_stage.py        # 28-field extraction + classification
│   │   │       └── dependency_stage.py      # SPO triple extraction
│   │   ├── services/
│   │   │   ├── folio/                       # FOLIO ontology (resolver, search, graph)
│   │   │   ├── llm/                         # LLM registry + provider implementations
│   │   │   ├── embedding/                   # Embedding service + FAISS index
│   │   │   ├── entity_ruler/                # Pattern builder + semantic ruler
│   │   │   ├── matching/                    # Aho-Corasick string matching
│   │   │   ├── concept/                     # LLM concept ID, branch judge, area of law
│   │   │   ├── individual/                  # Citation + entity extractors, deduplicator
│   │   │   ├── property/                    # Property matcher, deduplicator, LLM identifier
│   │   │   ├── quality/                     # Document type cross-check
│   │   │   ├── metadata/                    # Classifier, extractor, promoter
│   │   │   ├── normalization/               # Text chunking + sentence splitting
│   │   │   ├── reconciliation/              # EntityRuler + LLM merge logic
│   │   │   ├── dependency/                  # spaCy dependency parser
│   │   │   ├── streaming/                   # SSE implementation
│   │   │   └── testing/                     # Synthetic document generator
│   │   ├── middleware/
│   │   │   ├── error_handler.py             # Global exception handling
│   │   │   ├── rate_limit.py                # Request rate limiting
│   │   │   └── security.py                  # Header validation + CORS
│   │   └── storage/
│   │       ├── job_store.py                 # Atomic JSON job persistence
│   │       └── feedback_store.py            # Feedback persistence
│   ├── tests/                               # 586 tests across 45 files
│   └── pyproject.toml                       # Dependencies + build config
├── frontend/
│   └── index.html                           # Single-file SPA (vanilla JS, dark theme)
└── README.md
```

---

## Dependencies

### Core

| Library | Purpose |
|---------|---------|
| [FastAPI](https://fastapi.tiangolo.com/) | Web framework |
| [folio-python](https://pypi.org/project/folio-python/) | FOLIO ontology access (classes, properties, search) |
| [spaCy](https://spacy.io/) | NLP, entity ruler, NER, dependency parsing |
| [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Configuration via environment variables |

### NLP & Matching

| Library | Purpose |
|---------|---------|
| [pyahocorasick](https://pypi.org/project/pyahocorasick/) | Multi-pattern string matching (concepts + properties) |
| [faiss-cpu](https://github.com/facebookresearch/faiss) | Vector similarity search |
| [nupunkt](https://pypi.org/project/nupunkt/) | Sentence segmentation |
| [eyecite](https://pypi.org/project/eyecite/) | Legal citation parsing |
| [citeurl](https://pypi.org/project/citeurl/) | Citation normalization + URL resolution |

### Document Ingestion

| Library | Purpose |
|---------|---------|
| [PyMuPDF](https://pymupdf.readthedocs.io/) | PDF text extraction |
| [python-docx](https://python-docx.readthedocs.io/) | DOCX handling |
| [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) | HTML parsing |
| [markdown-it-py](https://pypi.org/project/markdown-it-py/) | Markdown parsing |
| [striprtf](https://pypi.org/project/striprtf/) | RTF format handling |
| [extract-msg](https://pypi.org/project/extract-msg/) | Email (EML/MSG) parsing |

### Export

| Library | Purpose |
|---------|---------|
| [pyarrow](https://arrow.apache.org/docs/python/) | Parquet export |
| [rdflib](https://rdflib.readthedocs.io/) | RDF/Turtle export |
| [openpyxl](https://openpyxl.readthedocs.io/) | Excel export |

### Infrastructure

| Library | Purpose |
|---------|---------|
| [uvicorn](https://www.uvicorn.org/) | ASGI server |
| [httpx](https://www.python-httpx.org/) | HTTP client for LLM APIs |
| [sse-starlette](https://pypi.org/project/sse-starlette/) | Server-Sent Events |

---

## License

See [LICENSE](LICENSE) for details.
