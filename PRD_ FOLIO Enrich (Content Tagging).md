# **Product Requirements Document: FOLIO Enrich: Legal Document Annotation Pipeline**

**Version:** 5.0 **Date:** February 21, 2026 **Author:** Damien Riehl / Claude Opus **Status:** Draft **Related Repository:** [`damienriehl/folio-mapper`](https://github.com/damienriehl/folio-mapper) — the existing FOLIO mapping tool whose backend pipeline this PRD extends

---

## **1\. Executive Summary**

This PRD specifies a pipeline that ingests legal documents in any common format — PDF, Microsoft Word, Markdown, plain text, HTML, RTF, email, or pasted text — annotates every recognized legal concept with tags from the FOLIO ontology (18,000+ standardized concepts), extracts syntactic relationships between co-occurring concepts, and delivers those annotations to end users as clickable spans. Clicking a tagged span reveals the FOLIO concept's label, definition, IRI, and position in the ontology hierarchy. The pipeline's ultimate output feeds a Legal Knowledge Graph: annotated concepts become graph nodes, and extracted syntactic relations become graph edges.

The pipeline builds on **FOLIO Mapper** ([`damienriehl/folio-mapper`](https://github.com/damienriehl/folio-mapper)), an existing tool that maps user taxonomies to the FOLIO ontology using fuzzy text matching and optional LLM-assisted ranking. This annotation pipeline reuses FOLIO Mapper's backend services — its FOLIO singleton, candidate search, hierarchy traversal, LLM provider integrations, and export infrastructure — while adding new upstream stages for multi-format ingestion, format-aware normalization, chunking, and document-wide span annotation. FOLIO Mapper already parses Excel, CSV, TSV, TXT, and Markdown for taxonomy input (`backend/app/services/file_parser.py`); this pipeline extends that ingestion capability to long-form legal documents.

The pipeline uses a **dual-path concept discovery** architecture. Two independent systems identify concepts in parallel: a deterministic **EntityRuler** (spaCy) scans the full document against all 18,000+ FOLIO labels, while the **LLM** reads chunks contextually to find concepts that require semantic understanding. Neither system sees the other's output. A **Reconciliation Layer** merges their results, using an LLM Judge to resolve conflicts — cases where the two systems disagree about whether a word functions as a legal concept in context. This parallel-then-reconcile design eliminates anchoring bias while maximizing recall.

The pipeline uses **NuPunkt-RS** for legal-domain sentence boundary detection, ensuring citations like "123 F.2d 456 (7th Cir. 2010)" remain intact during sentence-level chunking fallback, Judge context window extraction, and dependency parsing.

**Progressive rendering** delivers results to the user incrementally: high-confidence EntityRuler annotations appear within 2–3 seconds of upload, LLM results layer on per-chunk as they arrive, and the Judge refines multi-branch and conflict annotations in real time. The user starts reading annotated text within seconds, not minutes.

Deterministic **Aho-Corasick** string matching locates every occurrence in the document. FOLIO Mapper's backend resolves each concept against the ontology exactly once, then the pipeline stamps that resolution onto every occurrence. A **dependency parser** (spaCy) extracts syntactic relations between co-occurring annotated concepts — including FOLIO verbs like "denied," "overruled," "drafted" — producing Subject-Predicate-Object triples for knowledge graph construction. This **resolve-once, use-many** design eliminates hallucination from annotation output, minimizes LLM token cost, and reduces FOLIO resolution calls to the unique-concept count rather than the total-occurrence count.

A shared **embedding service** underpins multiple pipeline stages. Pre-computed FOLIO label embeddings (18,000+ vectors, cached on disk, rebuilt automatically when the FOLIO OWL file updates) enable: a **Semantic EntityRuler** that discovers synonym and paraphrase matches the literal EntityRuler misses; **embedding-assisted triage** that auto-resolves obvious Reconciliation and Branch Judge conflicts without LLM calls; and **embedding-augmented FOLIO resolution** that catches semantic matches when string similarity falls short. The embedding service runs locally by default (zero cost, no internet required) with optional cloud providers (Voyage AI `voyage-law-2`, OpenAI, Cohere) for higher legal-domain accuracy. Automatic fallback from cloud to local ensures the pipeline works identically in air-gapped environments.

A **Document Metadata Extraction** layer identifies what the document *is* — not just what concepts it contains. A Metadata Judge classifies the document type against FOLIO's Document Artifacts taxonomy (Motion to Dismiss, Commercial Lease, Court Opinion), extracts structured fields from targeted sections (court, judge, parties, case number, dates, claim types, governing law, outcome), and promotes body annotations to metadata based on structural position (an Actor annotation in a signature block becomes a signatory field). The metadata travels with every export.

The pipeline exports **12 formats** across two tiers. Tier 1 covers standard interchange: JSON, W3C JSON-LD, XML standoff, CSV, JSONL. Tier 2 targets enterprise integration: **Parquet** (corpus analytics in Pandas/Spark), **Elasticsearch bulk JSON** (concept-faceted search), **Neo4j CSV bundles** (knowledge graph import), **RAG-ready chunk JSON** (deterministic concept-filtered retrieval for LLM systems), RDF/Turtle, brat standoff, and HTML. Every export carries document metadata. A `?format=` parameter on the result API lets legal tech companies receive the exact format they need in a single HTTP call.

A **synthetic document generator** lets users test the pipeline without uploading real client documents. Users select a document type from a categorized tree (9 categories — Litigation, Contracts, Corporate, Regulatory, Law Firm Operations, Real Estate, IP, Estate Planning, Immigration — expanding to \~45 subtypes), a length (short/medium/long), and an optional jurisdiction. The LLM generates a realistic synthetic document that feeds directly into the pipeline.

---

## **2\. Problem Statement**

Legal professionals need to understand the legal concepts embedded in long, complex documents — contracts, briefs, regulations, opinions. Today, this understanding depends entirely on the reader's expertise. No tool automatically identifies, classifies, and defines the legal concepts woven throughout a document.

FOLIO provides the vocabulary: 18,000+ standardized legal concepts organized in a hierarchical ontology. This pipeline connects FOLIO's vocabulary to the text of actual legal documents, making every recognized concept visible, clickable, and defined.

---

## **3\. Goals and Non-Goals**

### **Goals**

1. **Accept any common legal document format** — PDF, Word (.docx/.doc), Markdown, plain text, HTML, RTF, email (.eml/.msg), or pasted text — through a unified ingestion layer  
2. **Annotate entire legal documents** — every section, clause, exhibit, and schedule — with FOLIO ontology tags  
3. **Produce clickable span annotations** that display FOLIO concept definitions on user interaction  
4. **Eliminate hallucination** from annotation output: the LLM names concepts and branches; deterministic string matching locates them; FOLIO Mapper resolves them  
5. **Minimize LLM token consumption** through context engineering: the LLM receives only FOLIO branch names (\~50 tokens of ontology context), not the full ontology  
6. **Resolve each unique concept once**, then apply that resolution to every occurrence across the entire document  
7. **Apply format-aware normalization** that fixes line-break artifacts in PDFs, cleans markup residue from HTML/RTF, and preserves clean structure from Word/Markdown — calibrating aggressiveness to each format's known problems  
8. **Preserve exact character offsets** from the canonical document text through every pipeline stage  
9. **Use dual-path concept discovery** — a deterministic EntityRuler and a contextual LLM running in parallel, with zero awareness of each other — to maximize recall without anchoring bias  
10. **Deliver progressive results** — high-confidence annotations appear within 2–3 seconds of upload; LLM and Judge results layer on incrementally  
11. **Extract syntactic relations** between co-occurring FOLIO concepts (including FOLIO verbs like "denied," "overruled," "drafted") to produce Subject-Predicate-Object triples for knowledge graph construction  
12. **Preserve legal citation integrity** using NuPunkt-RS for domain-specific sentence boundary detection  
13. **Discover synonyms and paraphrases** via embedding similarity against pre-computed FOLIO vectors — catching concepts that neither literal string matching nor the LLM identifies  
14. **Run fully offline** — all core pipeline stages operate on a single machine without internet access, using local embedding and NLP models; cloud providers available as optional accuracy upgrades with automatic local fallback

### **Non-Goals**

1. Training or fine-tuning custom models (pipeline uses general-purpose LLMs via API)  
2. \~\~Real-time annotation (batch processing acceptable for v1)\~\~ — **Revised:** progressive rendering delivers results incrementally; the pipeline is not fully real-time but streams partial results as they become available  
3. Editing or modifying the source document  
4. Supporting non-legal ontologies (FOLIO-specific)  
5. Full knowledge graph reasoning or inference (the pipeline produces triples; graph analytics are a downstream consumer concern)

---

## **4\. Users and Use Cases**

### **4.1 Individual Users**

| User | Use Case |
| ----- | ----- |
| **Associate attorney** | Uploads a 90-page commercial lease (PDF); clicks "force majeure" to see FOLIO's definition and ontology path; orients quickly in an unfamiliar practice area |
| **Litigator** | Pastes an opposing counsel's brief excerpt into the annotation tool; instantly sees every legal concept tagged and defined without uploading a file |
| **Compliance officer** | Forwards a regulatory alert email (.eml) to the annotation pipeline; receives tagged annotations highlighting every referenced legal concept |
| **Access-to-justice researcher** | Annotates court opinions scraped as HTML from public court websites to identify which legal concepts appear most frequently in pro se litigation |

### **4.2 Organizational Users — Legal Tech Companies**

Legal technology companies process documents at scale and integrate pipeline output into their own platforms. Each document processes individually; the export formats feed directly into the company's downstream infrastructure with zero transformation.

| Use Case | Workflow | Export Format |
| ----- | ----- | ----- |
| **Concept-faceted search** | Ingest each annotated document into Elasticsearch; enable users to filter by FOLIO concept, branch, court, document type | Elasticsearch bulk JSON |
| **Corpus analytics** | Concatenate per-document Parquet files into a dataset; run aggregation queries ("26% of Motions to Dismiss for Fraud are Granted") | Parquet |
| **RAG / retrieval** | Feed concept-tagged chunks into vector store; enable concept-filtered retrieval ("find all Default clauses in Commercial Leases") that is deterministic (graph-following), not purely probabilistic (embedding similarity) | RAG-ready chunk JSON |
| **Knowledge graph** | Import per-document nodes and relationships into Neo4j; run graph queries across the corpus ("MATCH (m:Motion)-\[:targets\]-\>(c:Claim) WHERE c.type \= 'Fraud'") | Neo4j CSV bundle |
| **API integration** | Call `GET /api/annotate/result/{job_id}?format=parquet` from a document processing pipeline; no frontend, no SSE, just HTTP in → annotated output out | Any format via `?format=` parameter |

### **4.3 Organizational Users — In-House Legal Departments**

In-house counsel teams process their own contract portfolios and litigation documents, typically 5K–50K documents in periodic batches.

| Use Case | Workflow | Export Format |
| ----- | ----- | ----- |
| **Contract review** | Upload a draft agreement from outside counsel; verify defined terms against FOLIO; review concept annotations with definitions | HTML (in-app), JSON |
| **Portfolio filtering** | Find all documents containing specific concept combinations (e.g., all contracts with "Force Majeure" AND "Termination") | JSON with concept summary, Parquet |
| **Portfolio analytics** | Understand concept distribution across contract portfolio; pivot tables in Excel or Jupyter | Parquet, CSV |
| **Case management** | Extract case metadata (court, judge, case number, parties, document type) for matter management system | JSON, CSV |

### **4.4 Organizational Users — Law Firms**

Law firms process documents per matter, typically 500–5,000 documents, with strong data security requirements.

| Use Case | Workflow | Export Format |
| ----- | ----- | ----- |
| **Matter research** | Map legal concepts in opposing counsel's brief; identify claim types, defenses, and cited authorities | HTML (in-app), JSON |
| **Brief drafting** | Find relevant provisions across precedent documents via concept-aware retrieval | RAG-ready chunk JSON |
| **Deposition preparation** | Annotate deposition transcripts; extract witness statements linked to specific legal concepts | JSON, HTML |
| **Case management integration** | Extract structured metadata (parties, judge, docket number, claim types) for firm's case management system | JSON, CSV |
| **Knowledge management** | Build firm-wide concept index from work product; enable concept-based search across matters | Elasticsearch bulk JSON |

---

## **5\. System Architecture**

### **5.1 Architecture Overview**

Document Input (any supported format)  
  │  
  ▼  
┌─────────────────────────────────────────────────┐  
│  STAGE 1: Multi-Format Ingestion \+ Normalization │  
│  (Format router → extractor → normalizer)        │  
└─────────────────────────┬───────────────────────┘  
                          │  
                          ▼  
┌─────────────────────────────────────────────────┐  
│  STAGE 2: Canonical Text Assembly \+ Freeze       │  
│  (Produces append-only string \+ offset map)      │  
└─────────────────────────┬───────────────────────┘  
                          │  
           ┌──────────────┼──────────────┐  
           │              │              │  
           ▼              │              ▼  
┌────────────────────┐    │   ┌────────────────────────────┐  
│  STAGE 2M:          │    │   │  DUAL-PATH SPLIT:           │  
│  Document Metadata  │    │   │  EntityRuler ∥ LLM Pipeline │  
│  Extraction         │    │   │  (see below)                │  
│                     │    │   │                              │  
│  Phase 1: Metadata  │    │   │                              │  
│  Judge classifies   │    │   │                              │  
│  document type from │    │   │                              │  
│  first 2-3 chunks   │    │   │                              │  
│                     │    │   │                              │  
│  Phase 2: Targeted  │    │   │                              │  
│  section extraction │    │   │                              │  
│                     │    │   │                              │  
│  Phase 3: Promote   │    │   │                              │  
│  annotations to     │    │   │                              │  
│  metadata (post-    │    │   │                              │  
│  pipeline)          │    │   │                              │  
└──────────┬──────────┘    │   └──────────────┬───────────────┘  
           │               │                  │  
           ▼               │                  ▼  
  (metadata streams via    │     ┌──────────────────────────┐  
   SSE; merges into        │     │  PATH A \+ PATH B          │  
   final JSON)             │     │  (parallel processing)    │  
                           │     └──────────────┬────────────┘  
           ┌──────────────┼──────────────┐     │  
           │ (PARALLEL)   │              │ (PARALLEL)  
           ▼              │              ▼  
┌────────────────────┐    │   ┌────────────────────────────┐  
│  PATH A:            │    │   │  PATH B: LLM Pipeline       │  
│  EntityRuler (2-3s) │    │   │                              │  
│  \+ Semantic         │    │   │  STAGE 3: Structure-Aware    │  
│  EntityRuler (6-13s)│    │   │    Chunking (NuPunkt-RS)     │  
│                     │    │   │  STAGE 4: LLM Concept ID     │  
│  Literal → exact    │    │   │    (per-chunk, streaming)    │  
│  matches (18K FOLIO)│    │   │                              │  
│  Semantic → synonym │◄───┤   │  → Results stream per-chunk  │  
│  matches (embedding │    │   │    as LLM calls complete     │  
│  similarity via     │    │   │                              │  
│  shared             │    │   │                              │  
│  EmbeddingService)  │    │   │                              │  
└──────────┬──────────┘    │   └──────────────┬───────────────┘  
           │               │                  │  
           │  ┌────────────▼──────────────┐   │  
           └─►│  STAGE 4.5: Reconciliation │◄──┘  
              │  Aligner \+ Embedding       │  
              │  Triage \+ Judge            │  
              │  (embedding auto-resolves  │  
              │   obvious cases; Judge     │◄──┐  
              │   handles ambiguous ones)  │   │  
              └────────────┬──────────────┘   │  
                           │                  │  
           ┌───────────────┴──────────────────┘  
           │  
           ▼  
┌──────────────────────────────────────────────────┐  
│  EmbeddingService (shared singleton)              │  
│  Pre-computed FOLIO embeddings (18K, FAISS index) │  
│  Local default (all-mpnet-base-v2) | Cloud opt.   │  
│                                                    │  
│  Consumers: Semantic EntityRuler, Reconciliation   │  
│   triage, Resolution fallback, Branch Judge triage │  
└──────────────────────────────────────────────────┘  
                           │  
                           ▼  
┌─────────────────────────────────────────────────┐  
│  STAGE 5: Concept Deduplication \+ FOLIO          │  
│  Resolution (resolve once per unique concept)    │  
│  (Embedding fallback for low-confidence matches) │  
└─────────────────────────┬───────────────────────┘  
                          │  
                          ▼  
┌─────────────────────────────────────────────────┐  
│  STAGE 6: Global String Matching                 │  
│  (Aho-Corasick single-pass scan \+ word-boundary  │  
│   validation — locates every occurrence)          │  
│  (Incremental per-chunk \+ final full-doc scan)   │  
└─────────────────────────┬───────────────────────┘  
                          │  
                          ▼  
┌─────────────────────────────────────────────────┐  
│  STAGE 6.5: Context-Aware Branch Judge (LLM)     │  
│  (Embedding triage auto-resolves obvious cases;  │  
│   LLM Judge handles ambiguous multi-branch       │  
│   concepts — fires per-chunk)                    │  
└─────────────────────────┬───────────────────────┘  
                          │  
                          ▼  
┌─────────────────────────────────────────────────┐  
│  STAGE 6.75: Dependency Parsing (spaCy)          │  
│  (Extract syntactic relations between            │  
│   co-occurring FOLIO concepts — produces         │  
│   SPO triples for Knowledge Graph)               │  
└─────────────────────────┬───────────────────────┘  
                          │  
                          ▼  
┌─────────────────────────────────────────────────┐  
│  STAGE 7: Annotation \+ Triple \+ Metadata         │  
│  Persistence                                     │  
│  (JSON annotation layer \+ relation triples       │  
│   \+ document metadata from Phase 1/2/3           │  
│   → progressive frontend rendering via SSE       │  
│   → user resurrection with dual-panel FOLIO tree │  
│   → 12 export formats including Parquet,         │  
│     Elasticsearch, Neo4j, RAG chunks)            │  
└─────────────────────────────────────────────────┘

### **5.2 Key Architectural Principles**

**Principle 1: The LLM returns concept text \+ branch only.**

The LLM's job: read natural language in context, identify legal concepts, classify each into a FOLIO branch. It returns short strings and branch names. It never returns character offsets, FOLIO IRIs, or definitions.

Why no offsets: LLMs unreliably count characters. Every offset the LLM produces carries hallucination risk — off-by-one errors, fabricated positions, wrong boundaries. Deterministic string matching (Aho-Corasick automaton with word-boundary validation) locates concepts with zero error.

Why no IRIs or definitions: accurate IRI resolution would require the full ontology in context (\~500K tokens). `folio-python` resolves IRIs deterministically.

**Principle 2: Resolve once, use many.**

A 90-page lease might contain "Landlord" 200 times. The pipeline resolves "Landlord" against `folio-python` exactly once, caches the result (IRI, label, definition, branch path), and stamps that resolution onto all 200 occurrences. This reduces FOLIO API calls from total-occurrence-count to unique-concept-count — typically a 10–50x reduction.

**Principle 3: Dual-path concept discovery — parallel, independent, reconciled.**

Two systems discover concepts independently, in parallel, with zero awareness of each other:

| Path | System | Strength | Blind Spot |
| ----- | ----- | ----- | ----- |
| **Path A** | EntityRuler (spaCy \+ 18K FOLIO labels) | Exact label matches; 2–3 seconds for 500 pages; finds every literal FOLIO term | No context sensitivity; matches "Interest" everywhere including non-legal usage |
| **Path B** | LLM (per-chunk, contextual) | Contextual discovery ("the agreement" → Contract); branch classification; understands ambiguous terms | Slower (minutes); may miss concepts; token cost |

Neither path sees the other's output. A Reconciliation Layer merges their results after both complete (per-chunk for progressive rendering). An LLM Judge resolves conflicts — cases where one path found a concept the other ignored, or where both found it but classified it differently. This design eliminates anchoring bias: the LLM operates at full capability without being primed by the EntityRuler's list.

**Principle 4: Progressive rendering — show everything, signal certainty.**

The canonical text is append-only. Once characters 0–5,000 are written, they never change. This invariant enables progressive rendering: annotations on early text remain valid as later text arrives. The pipeline streams results via Server-Sent Events (SSE). ALL matches display immediately — the visual treatment communicates certainty level, not whether the match is visible:

| Time | What the User Sees |
| ----- | ----- |
| 0–1 sec | Document text appears |
| 2–3 sec | ALL EntityRuler annotations appear: high-confidence with solid highlights; low-confidence with lighter highlights and uncertainty indicators ("?" badge, dotted border) |
| 8–15 sec | First chunk's LLM results arrive; reconciliation upgrades preliminary annotations to "confirmed" (solid highlight) or transitions them to "rejected" (dimmed but visible, with "Resurrect" affordance); LLM-discovered contextual concepts appear as confirmed |
| 15–60 sec | Remaining chunks reconcile progressively; rejected annotations accumulate but remain visible |
| 1–5 min | Full document complete with final Aho-Corasick cross-check, Judge verdicts, and dependency-parsed triples |

Three annotation states exist throughout: **preliminary** (awaiting confirmation), **confirmed** (pipeline verified), and **rejected** (Judge disagreed, but user can resurrect). Rejected annotations never disappear — the user can override the Judge by clicking "Resurrect," which opens a dual-panel FOLIO tree selection using FOLIO Mapper's existing tree components (see §6.8.4).

**Principle 5: Annotations feed a Knowledge Graph.**

The pipeline produces two layers of output: (1) **span annotations** — each text span tagged with a FOLIO IRI, branch, and definition; and (2) **relation triples** — Subject-Predicate-Object triples extracted from sentences containing 2+ annotated FOLIO concepts. FOLIO includes verbs ("denied," "overruled," "drafted") as ontology concepts, enabling triple extraction where the predicate is itself a FOLIO IRI. The span annotations become graph nodes; the relation triples become graph edges. Export formats (RDF/Turtle, JSON-LD) carry both layers.

**Principle 6: Legal-domain sentence boundary detection.**

Legal text breaks standard sentence detectors. Citations like "123 F.2d 456 (7th Cir. 2010)" contain periods that naive splitters treat as sentence endings. NuPunkt-RS — a Rust-backed sentence boundary detector trained on legal corpora — preserves citation integrity. The pipeline uses NuPunkt-RS wherever sentence boundaries matter: chunker fallback splitting, Judge context window extraction, and dependency parsing sentence segmentation.

**Principle 7: Shared embedding infrastructure — local by default, cloud optional.**

A single `EmbeddingService` provides pre-computed FOLIO label embeddings and on-demand text embedding to every pipeline stage that needs semantic similarity. The service:

* Pre-computes embeddings for all 18,000+ FOLIO labels at startup (cached to disk, rebuilt only when the FOLIO OWL file updates)  
* Provides `embed(text)`, `similarity(text, iri)`, and `nearest_neighbors(text, k, branch_filter)` methods  
* Runs locally by default (`all-mpnet-base-v2`, zero cost, no internet) with optional cloud providers for higher legal-domain accuracy  
* Falls back from cloud to local automatically if the network is unavailable

Four pipeline stages consume the shared embedding service:

| Stage | Use Case | What Gets Embedded |
| ----- | ----- | ----- |
| **2C Semantic EntityRuler** | Synonym/paraphrase discovery | Document noun phrases vs. FOLIO label index |
| **4.5 Reconciliation** | Triage: auto-resolve obvious conflicts without Judge LLM calls | Context sentences vs. FOLIO concept definitions |
| **5 Resolution** | Fallback when `rapidfuzz` string similarity is low | Concept text vs. FOLIO label index |
| **6.5 Branch Judge** | Triage: auto-resolve obvious branch assignments without Judge LLM calls | Context sentences vs. branch definition embeddings |

Pre-computing FOLIO embeddings costs \~5 seconds and $0.00 (local model). The cache sits alongside `folio-python`'s OWL cache at `~/.folio/cache/`. Cache key \= `{model_name}_{owl_file_hash}` — switching models creates a new cache without destroying existing ones. Even with weekly FOLIO OWL updates, the annual re-embedding cost is $0.00 (local) or under $2.00 (cloud).

**Principle 8: No hallucination reaches the user.**

Every annotation in the output satisfies two deterministic checks: (1) the concept text appears verbatim in the canonical document, and (2) `folio-python` resolved it to a valid FOLIO IRI. If either check fails, the annotation gets discarded or flagged. The LLM influences *which* concepts the pipeline looks for, but deterministic tooling controls *what reaches the user*.

**Principle 9: Separation of concerns.**

| Component | Responsibility | Can Hallucinate? |
| ----- | ----- | ----- |
| **EntityRuler** | Deterministic scan of 18K FOLIO labels; fast; context-blind | No — exact string matching against ontology labels |
| **Semantic EntityRuler** | Synonym/paraphrase discovery via embedding similarity against FOLIO label index | No — deterministic vector similarity with configurable threshold |
| **EmbeddingService** | Shared embedding infrastructure: pre-computed FOLIO vectors, on-demand text embedding, nearest-neighbor search | No — mathematical similarity computation |
| **LLM** | Name concepts and suggest plausible branches (1:many); contextual discovery | Yes — but extra branches get filtered by deterministic resolution; missing branches are unrecoverable |
| **Reconciliation Layer** | Merge dual-path results; categorize conflicts; embedding triage for obvious cases | No — deterministic alignment logic \+ vector similarity thresholds |
| **Reconciliation Judge** | Resolve ambiguous EntityRuler/LLM conflicts using surrounding context | Yes — but limited to keep/reject decisions on known FOLIO labels; only fires when embedding triage is inconclusive |
| **Metadata Judge** | Classify document type against FOLIO Document Artifacts taxonomy; extract structured fields (court, judge, parties, dates) from targeted document sections | Yes — but outputs are structured fields validated against FOLIO labels and common metadata patterns |
| **String matching** | Locate every occurrence in the document; produce overlapping annotations for nested concepts | No — Aho-Corasick automaton \+ word-boundary validation |
| **FOLIO Mapper** | Resolve each (concept, branch) pair to a FOLIO IRI \+ definition; discard pairs with no match; embedding fallback for low-confidence matches | No — deterministic ontology search \+ vector similarity |
| **NuPunkt-RS** | Sentence boundary detection preserving legal citation integrity | No — statistical model trained on legal corpora |
| **Dependency parser** | Extract syntactic relations (SPO triples) between co-occurring FOLIO concepts | No — deterministic parse tree traversal |
| **Canonical text** | Provide ground truth at every offset | No — frozen, append-only |
| **Frontend** | Render clickable spans with progressive updates via SSE | No — pure rendering |

---

## **5A. FOLIO Mapper Integration**

### **5A.1 What FOLIO Mapper Provides**

[FOLIO Mapper](https://github.com/damienriehl/folio-mapper) (`damienriehl/folio-mapper`) already implements the core FOLIO resolution infrastructure this pipeline needs. Rather than rebuild these capabilities, the annotation pipeline reuses FOLIO Mapper's backend as its resolution engine.

**FOLIO Mapper's backend services relevant to this pipeline:**

| FOLIO Mapper Component | Path in Repository | What This Pipeline Uses It For |
| ----- | ----- | ----- |
| **FOLIO singleton \+ search** | `backend/app/services/folio_service.py` | Loading the FOLIO ontology; fuzzy label \+ synonym matching; hierarchy traversal; branch filtering |
| **Candidate search endpoint** | `POST /api/mapping/candidates` | Stage 5 concept resolution — send extracted span text, receive ranked FOLIO concept matches with confidence scores |
| **Concept detail endpoint** | `POST /api/mapping/detail` | Fetching full concept info (definition, hierarchy path, children, siblings, translations) for the annotation JSON |
| **Concept lookup by IRI** | `POST /api/mapping/lookup` | Validating resolved IRIs; enriching cached resolutions |
| **LLM pipeline stages** | `backend/app/services/pipeline/` | Stage 4 LLM concept identification reuses FOLIO Mapper's LLM provider abstraction (9 providers: OpenAI, Anthropic, Gemini, Mistral, Cohere, Llama, Ollama, LM Studio, Custom) |
| **LLM provider implementations** | `backend/app/services/llm/` | Provider connection, model discovery, prompt execution — already supporting the 9 providers |
| **Export infrastructure** | `backend/app/services/export_service.py` | Stage 7 export — FOLIO Mapper already generates CSV, Excel, JSON, RDF/Turtle, JSON-LD, Markdown, HTML, PDF |
| **Branch colors \+ display order** | `packages/core/src/folio/` | FOLIO branch metadata (24 branches, color coding, display order) used in the LLM prompt and annotation output |
| **Mapping types \+ score cutoffs** | `packages/core/src/mapping/` | Confidence score calculation; color-coded badges (green/yellow/orange) reused in annotation confidence display |
| **Pydantic request/response models** | `backend/app/models/` | API contract types shared between annotation pipeline and FOLIO Mapper |

### **5A.2 FOLIO Mapper's Mapping Pipeline**

FOLIO Mapper's existing LLM-enhanced pipeline operates in stages that directly parallel this annotation pipeline's resolution needs:

| FOLIO Mapper Stage | What It Does | How This Pipeline Reuses It |
| ----- | ----- | ----- |
| **Stage 1 — Local search** | Branch-scoped fuzzy matching with synonym expansion and fallback against all \~18,300 FOLIO classes | **Stage 5 resolution**: send each unique concept text \+ branch to this stage; receive ranked FOLIO candidates |
| **Stage 3 — Judge validation** | LLM reviews each candidate, adjusts scores, rejects false positives | **Optional quality pass**: after initial resolution, the LLM judge can validate ambiguous matches (confidence \< threshold) |

The key code paths in FOLIO Mapper's backend:

backend/  
  app/  
    services/  
      folio\_service.py          ← FOLIO singleton: load, search, hierarchy  
      pipeline/                 ← Stage orchestration (Stages 0–3)  
      llm/                      ← 9 LLM provider implementations  
    routers/  
      mapping\_router.py         ← /api/mapping/\* endpoints  
      pipeline\_router.py        ← /api/pipeline/map endpoint  
      llm\_router.py             ← /api/llm/\* endpoints  
    models/                     ← Pydantic request/response schemas

### **5A.3 How the Annotation Pipeline Calls FOLIO Mapper**

The annotation pipeline invokes FOLIO Mapper's backend through its existing API endpoints. Claude Code should reference these endpoints when implementing Stages 4–6:

**For concept resolution (Stage 5):**

\# Call FOLIO Mapper's candidate search endpoint  
\# See: backend/app/routers/mapping\_router.py → POST /api/mapping/candidates  
\# Called once per unique (concept\_text, branch) pair.  
\# For "United States" with branches \["Locations", "Governmental Bodies"\],  
\# this endpoint gets called TWICE — once per branch.  
response \= await client.post("/api/mapping/candidates", json={  
    "text": "United States",        \# extracted span text  
    "branches": \["Locations"\],       \# ONE branch per call  
    "top\_n": 5                       \# number of candidates  
})  
\# Returns ranked candidates with IRIs, labels, definitions, scores  
\# If no match in this branch → resolution\_cache stores {resolved: False}

**For concept detail enrichment (Stage 7):**

\# Call FOLIO Mapper's detail endpoint for full concept info  
\# See: backend/app/routers/mapping\_router.py → POST /api/mapping/detail  
response \= await client.post("/api/mapping/detail", json={  
    "iri": "folio:R8pNPutX0TN6DlEqkyZuxSw"  
})  
\# Returns: definition, hierarchy path, children, siblings, translations

**For LLM concept identification (Stage 4):**

\# Reuse FOLIO Mapper's LLM provider abstraction  
\# See: backend/app/services/llm/ → provider implementations  
\# See: backend/app/routers/llm\_router.py → POST /api/llm/test-connection  
\# The annotation pipeline's LLM prompt (Stage 4\) runs through  
\# the same provider infrastructure, supporting all 9 providers

### **5A.4 New Components This Pipeline Adds**

The annotation pipeline extends FOLIO Mapper with components that don't exist in the current codebase:

| New Component | Responsibility | Where to Add in FOLIO Mapper |
| ----- | ----- | ----- |
| **Ingestion router** | Detect input format, dispatch to correct extractor | `backend/app/services/ingestion/router.py` (new) |
| **PDF extractor** | Docling structural extraction \+ aggressive line-break normalization | `backend/app/services/ingestion/pdf_extractor.py` (new) |
| **Word extractor** | python-docx paragraph/table/heading extraction | `backend/app/services/ingestion/docx_extractor.py` (new) |
| **Markdown extractor** | markdown-it parsing to structured elements | `backend/app/services/ingestion/markdown_extractor.py` (new) |
| **HTML extractor** | BeautifulSoup tag stripping \+ structure detection | `backend/app/services/ingestion/html_extractor.py` (new) |
| **Plain text extractor** | Direct read with paragraph detection | `backend/app/services/ingestion/text_extractor.py` (new) |
| **RTF extractor** | striprtf conversion \+ structure detection | `backend/app/services/ingestion/rtf_extractor.py` (new) |
| **Email extractor** | Python email library for .eml; msg-parser for .msg | `backend/app/services/ingestion/email_extractor.py` (new) |
| **Paste handler** | Accept raw text via API, treat as plain text | `backend/app/services/ingestion/paste_handler.py` (new) |
| **Format-aware normalizer** | Line-break classification calibrated per source format | `backend/app/services/ingestion/normalizer.py` (new) |
| **Canonical text assembler** | Immutable string assembly \+ offset map (format-agnostic) | `backend/app/services/canonical_service.py` (new) |
| **Structure-aware chunker** | Zero-overlap chunking at section boundaries | `backend/app/services/chunking_service.py` (new) |
| **Annotation LLM prompt** | Concept-text \+ branch identification prompt | `backend/app/services/pipeline/annotation_stage.py` (new) |
| **Resolution cache** | Resolve-once-use-many concept caching | `backend/app/services/resolution_cache.py` (new) |
| **Global string matcher** | Aho-Corasick single-pass multi-pattern matching with character-class boundary validation | `backend/app/services/span_locator.py` (new) |
| **Context-aware Judge** | Disambiguate multi-branch concepts using surrounding sentences | `backend/app/services/judge_service.py` (new) |
| **Reconciliation aligner \+ Judge** | Merge EntityRuler and LLM results; Judge resolves conflicts using context | `backend/app/services/reconciliation_service.py` (new) |
| **EntityRuler** | Deterministic FOLIO label scan (18K labels, spaCy EntityRuler) | `backend/app/services/entity_ruler_service.py` (new) |
| **Semantic EntityRuler** | Synonym/paraphrase discovery via embedding similarity | `backend/app/services/semantic_entity_ruler.py` (new) |
| **EmbeddingService** | Shared embedding infrastructure: pre-computed FOLIO vectors, provider abstraction, FAISS index, local/cloud/fallback | `backend/app/services/embedding/` (new directory) |
| **Document Metadata Extractor** | Three-phase metadata extraction: document type classification, structured field extraction from targeted sections, annotation promotion | `backend/app/services/metadata_extractor.py` (new), `backend/app/services/metadata_judge.py` (new) |
| **Synthetic Document Generator** | LLM-based generation of realistic synthetic legal documents by type, length, and jurisdiction for pipeline testing without real client data | `backend/app/services/synthetic_generator.py` (new) |
| **NuPunkt-RS sentence detector** | Legal-domain sentence boundary detection for chunking fallback, Judge context, and dependency parsing | `backend/app/services/sentence_detector.py` (new) |
| **Dependency parser** | Extract syntactic relations between co-occurring FOLIO concepts for knowledge graph triples | `backend/app/services/relation_extractor.py` (new) |
| **Annotation export** | Serialize annotations \+ triples to 8+ output formats for downstream systems | `backend/app/services/annotation_export_service.py` (new) |
| **Annotation API router** | `/api/annotate/*` endpoints for the annotation pipeline | `backend/app/routers/annotation_router.py` (new) |
| **Annotation models** | Pydantic schemas for annotation requests/responses | `backend/app/models/annotation.py` (new) |

### **5A.5 Extended Architecture (FOLIO Mapper \+ Annotation Pipeline)**

folio-mapper/                          \# Existing repository  
├── packages/  
│   ├── core/                          \# Shared types (EXISTING)  
│   │   └── src/  
│   │       ├── folio/                 \# Branch colors, display order ← REUSED  
│   │       ├── mapping/              \# Score cutoffs ← REUSED  
│   │       ├── llm/                  \# LLM provider types ← REUSED  
│   │       ├── pipeline/             \# Pipeline types ← REUSED  
│   │       ├── export/               \# Export types ← REUSED  
│   │       └── annotation/           \# ★ NEW: Annotation-specific types  
│   └── ui/                           \# React components (EXISTING)  
│       └── src/components/  
│           └── annotation/           \# ★ NEW: Annotation viewer components  
├── apps/  
│   └── web/                          \# Main React app (EXISTING)  
│       └── src/  
│           ├── hooks/  
│           │   └── useAnnotation.ts  \# ★ NEW: Annotation state management  
│           └── store/  
│               └── annotationStore.ts \# ★ NEW: Annotation Zustand store  
└── backend/                          \# FastAPI backend (EXISTING)  
    ├── app/  
    │   ├── main.py                   \# CORS, router registration ← ADD annotation\_router  
    │   ├── models/  
    │   │   └── annotation.py         \# ★ NEW: Annotation Pydantic models  
    │   ├── routers/  
    │   │   ├── mapping\_router.py     \# /api/mapping/\* ← REUSED by resolution  
    │   │   ├── pipeline\_router.py    \# /api/pipeline/\* ← REUSED for LLM  
    │   │   ├── llm\_router.py         \# /api/llm/\* ← REUSED for providers  
    │   │   └── annotation\_router.py  \# ★ NEW: /api/annotate/\* endpoints  
    │   └── services/  
    │       ├── folio\_service.py      \# FOLIO singleton ← REUSED for resolution  
    │       ├── file\_parser.py        \# Excel/CSV/TSV/TXT parsing ← REUSED for text formats  
    │       ├── llm/                  \# LLM providers ← REUSED  
    │       ├── pipeline/             \# Mapping pipeline ← REUSED  
    │       │   └── annotation\_stage.py \# ★ NEW: Annotation LLM prompt  
    │       ├── ingestion/            \# ★ NEW: Multi-format ingestion layer  
    │       │   ├── \_\_init\_\_.py  
    │       │   ├── router.py         \# Format detection \+ dispatch  
    │       │   ├── normalizer.py     \# Format-aware line-break normalization  
    │       │   ├── pdf\_extractor.py  \# Docling-based PDF extraction  
    │       │   ├── docx\_extractor.py \# python-docx Word extraction  
    │       │   ├── markdown\_extractor.py  \# markdown-it parsing  
    │       │   ├── html\_extractor.py \# BeautifulSoup extraction  
    │       │   ├── text\_extractor.py \# Plain text with paragraph detection  
    │       │   ├── rtf\_extractor.py  \# striprtf conversion  
    │       │   ├── email\_extractor.py \# .eml/.msg extraction  
    │       │   └── paste\_handler.py  \# Pasted text handling  
    │       ├── canonical\_service.py  \# ★ NEW: Text assembly \+ freeze  
    │       ├── chunking\_service.py   \# ★ NEW: Structure-aware chunking  
    │       ├── resolution\_cache.py   \# ★ NEW: Resolve-once cache  
    │       ├── span\_locator.py       \# ★ NEW: Global string matching  
    │       ├── judge\_service.py      \# ★ NEW: Context-aware branch disambiguation  
    │       ├── reconciliation\_service.py  \# ★ NEW: Dual-path merge \+ conflict Judge  
    │       ├── entity\_ruler\_service.py    \# ★ NEW: spaCy EntityRuler with FOLIO labels  
    │       ├── sentence\_detector.py       \# ★ NEW: NuPunkt-RS wrapper  
    │       ├── relation\_extractor.py      \# ★ NEW: spaCy dependency parsing for KG triples  
    │       └── annotation\_export\_service.py  \# ★ NEW: 8-format annotation \+ triple export  
    └── tests/  
        ├── ...                       \# Existing 155 tests  
        ├── test\_ingestion/           \# ★ NEW: Per-format extraction tests  
        └── test\_annotation/          \# ★ NEW: Annotation pipeline tests

### **5A.6 New API Endpoints**

| Method | Endpoint | Description | Calls FOLIO Mapper |
| ----- | ----- | ----- | ----- |
| POST | `/api/annotate/upload` | Upload file (any supported format), return job ID | — |
| POST | `/api/annotate/paste` | Submit pasted text, return job ID | — |
| GET | `/api/annotate/status/{job_id}` | Poll processing status | — |
| GET | `/api/annotate/result/{job_id}` | Retrieve annotation JSON | — |
| GET | `/api/annotate/canonical/{job_id}` | Retrieve canonical text | — |
| GET | `/api/annotate/unresolved/{job_id}` | Retrieve unresolved concepts | — |
| POST | `/api/annotate/resolve-manual` | Manually resolve a flagged concept | `POST /api/mapping/candidates` |
| POST | `/api/annotate/export` | Export annotations (12 formats: JSON, JSON-LD, XML, CSV, JSONL, Turtle, brat, HTML, Parquet, Elasticsearch, Neo4j CSV, RAG chunks) | FOLIO Mapper's export infrastructure |
| POST | `/api/annotate/batch-export` | Export annotations across multiple jobs (merged or individual) | FOLIO Mapper's export infrastructure |

---

### **6.0 Job Lifecycle Management**

#### **6.0.1 Job States**

Every annotation request creates a **job** with a unique `job_id` (UUID v4). Jobs progress through a defined lifecycle:

| State | Description | Transitions To |
| ----- | ----- | ----- |
| **queued** | Job created, awaiting processing | `processing`, `failed` |
| **processing** | Pipeline executing (current stage tracked in `status.stage`) | `completed`, `failed` |
| **completed** | All stages finished successfully; results available | `expired` |
| **failed** | Pipeline encountered an unrecoverable error; partial results may be available | `queued` (retry) |
| **expired** | Job data cleaned up after retention period | (terminal) |

#### **6.0.2 Job Persistence (v1)**

Jobs persist to the local filesystem under a configurable directory:

\~/.folio/jobs/
  {job\_id}/
    job.json              \# Job metadata: state, timestamps, source\_format, filename
    canonical.txt         \# Frozen canonical text (Stage 2 output)
    offset\_map.json       \# Structural offset map
    chunks.json           \# Stage 3 chunk definitions
    entity\_ruler.json     \# Path A results
    llm\_raw/              \# Per-chunk LLM responses (Stage 4)
      chunk\_0.json
      chunk\_1.json
      ...
    reconciliation.json   \# Stage 4.5 merge results
    resolution\_cache.json \# Stage 5 resolve-once cache
    annotations.json      \# Final annotation layer
    triples.json          \# SPO triples
    metadata.json         \# Document metadata (Phases 1-3)
    spot\_check.json       \# Normalization spot-check report

Each stage writes its output atomically (write to `.tmp`, then rename) to prevent corruption from crashes. The resolution cache is **per-document**, not shared across documents — different documents may resolve the same concept text differently based on surrounding context and Judge verdicts.

#### **6.0.3 Error Recovery**

If the pipeline fails mid-processing:

| Failure Point | Recovery Behavior |
| ----- | ----- |
| **Stage 1-2** (ingestion/canonical) | Job marked `failed`; user must re-upload. No partial results. |
| **Stage 3** (chunking) | Job marked `failed`; canonical text preserved; retry re-chunks from canonical text. |
| **Stage 4** (LLM, mid-chunk) | Completed chunks preserved. Retry resumes from the first unprocessed chunk. LLM responses are saved per-chunk. |
| **Stage 4.5-5** (reconciliation/resolution) | Retry re-runs from reconciliation using preserved EntityRuler + LLM results. |
| **Stage 6-7** (matching/persistence) | Retry re-runs from string matching using preserved resolution cache. |

Retry is triggered via `POST /api/annotate/retry/{job_id}`. The endpoint identifies the last successfully completed stage and resumes from the next stage.

#### **6.0.4 Job Cleanup**

| Policy | Default | Configurable |
| ----- | ----- | ----- |
| **Completed job retention** | 7 days | `JOB_RETENTION_DAYS` env var |
| **Failed job retention** | 3 days | `FAILED_JOB_RETENTION_DAYS` env var |
| **Cleanup frequency** | Hourly background task | — |
| **Manual deletion** | `DELETE /api/annotate/job/{job_id}` | — |

The cleanup task removes expired job directories. Uploaded source documents are deleted immediately after canonical text assembly (Stage 2 completion) — the pipeline retains only the canonical text, never the original file.

#### **6.0.5 Concurrent Processing**

The pipeline supports concurrent processing of multiple documents. The EntityRuler spaCy pipeline and EmbeddingService singleton are read-only after initialization and are thread-safe for concurrent use. Each job maintains its own resolution cache, LLM state, and annotation output. Concurrency is bounded by `MAX_CONCURRENT_JOBS` (default: 3) to manage memory pressure from simultaneously loaded canonical texts and in-flight LLM calls.

---

### **6.1 Stage 1: Multi-Format Ingestion \+ Normalization**

#### **6.1.1 Supported Input Formats**

| Format | Extensions | Extractor | Library | Normalization Severity |
| ----- | ----- | ----- | ----- | ----- |
| **PDF** | `.pdf` | `pdf_extractor.py` | Docling (IBM) | **Aggressive** — soft-wrap rejoining, dehyphenation, page-break repair |
| **Microsoft Word** | `.docx`, `.doc` | `docx_extractor.py` | python-docx (`.docx`); antiword or LibreOffice CLI (`.doc`) | **Light** — Word stores semantic paragraphs; normalize only stray `\r\n` |
| **Markdown** | `.md` | `markdown_extractor.py` | markdown-it-py | **Minimal** — strip markup, preserve structure; Markdown line breaks are intentional |
| **Plain text** | `.txt` | `text_extractor.py` | Built-in `open()` | **Light** — paragraph detection from blank lines; no dehyphenation |
| **HTML** | `.html`, `.htm` | `html_extractor.py` | BeautifulSoup 4 | **Moderate** — strip tags, collapse whitespace, detect headings/lists/tables |
| **RTF** | `.rtf` | `rtf_extractor.py` | striprtf2 | **Moderate** — convert to text, then apply light normalization |
| **Email** | `.eml`, `.msg` | `email_extractor.py` | Python `email` (`.eml`); msg-parser (`.msg`) | **Light** — extract body (prefer HTML part → plain text fallback); strip signatures/disclaimers |
| **Pasted text** | (none) | `paste_handler.py` | Direct string | **Minimal** — normalize `\r\n` to `\n`; detect paragraphs from blank lines |

**Additional formats to consider for future versions:** XML (legal XML standards like Akoma Ntoso), EPUB, ODT (LibreOffice), scanned images without PDF wrapper (TIFF/PNG → OCR).

#### **6.1.2 The Format Router**

Every input enters the pipeline through a single function that detects the format, dispatches to the correct extractor, and returns a uniform list of `TextElement` objects.

\# backend/app/services/ingestion/router.py

from dataclasses import dataclass  
from enum import Enum  
from pathlib import Path  
import magic  \# python-magic for MIME detection

class InputFormat(Enum):  
    PDF \= "pdf"  
    DOCX \= "docx"  
    DOC \= "doc"  
    MARKDOWN \= "markdown"  
    PLAIN\_TEXT \= "plain\_text"  
    HTML \= "html"  
    RTF \= "rtf"  
    EML \= "eml"  
    MSG \= "msg"  
    PASTE \= "paste"

@dataclass  
class TextElement:  
    """  
    Universal intermediate representation.  
    Every extractor produces a list of these — regardless of source format.  
    Stages 2–7 operate exclusively on TextElement lists.  
    """  
    id: str  
    text: str                      \# normalized text content  
    element\_type: str              \# "heading", "paragraph", "table\_cell",  
                                   \# "list\_item", "blockquote", "code\_block"  
    section\_path: str | None       \# e.g., "Article II \> §2.3(a)"  
    page: int | None               \# page number (PDF/Word) or None  
    level: int | None              \# heading level (1–6) or None  
    source\_format: InputFormat     \# which extractor produced this element

def detect\_format(file\_path: Path | None, mime\_type: str | None,  
                  is\_paste: bool \= False) \-\> InputFormat:  
    """  
    Detect input format from file extension, MIME type, or paste flag.  
    Precedence: explicit paste flag → MIME type → file extension.  
    """  
    if is\_paste:  
        return InputFormat.PASTE

    ext\_map \= {  
        ".pdf": InputFormat.PDF,  
        ".docx": InputFormat.DOCX,  
        ".doc": InputFormat.DOC,  
        ".md": InputFormat.MARKDOWN,  
        ".markdown": InputFormat.MARKDOWN,  
        ".txt": InputFormat.PLAIN\_TEXT,  
        ".text": InputFormat.PLAIN\_TEXT,  
        ".html": InputFormat.HTML,  
        ".htm": InputFormat.HTML,  
        ".rtf": InputFormat.RTF,  
        ".eml": InputFormat.EML,  
        ".msg": InputFormat.MSG,  
    }

    if file\_path:  
        ext \= file\_path.suffix.lower()  
        if ext in ext\_map:  
            return ext\_map\[ext\]

    \# Fallback: MIME sniffing  
    if file\_path and file\_path.exists():  
        detected \= magic.from\_file(str(file\_path), mime=True)  
        mime\_map \= {  
            "application/pdf": InputFormat.PDF,  
            "application/vnd.openxmlformats-officedocument"  
            ".wordprocessingml.document": InputFormat.DOCX,  
            "application/msword": InputFormat.DOC,  
            "text/markdown": InputFormat.MARKDOWN,  
            "text/plain": InputFormat.PLAIN\_TEXT,  
            "text/html": InputFormat.HTML,  
            "text/rtf": InputFormat.RTF,  
            "application/rtf": InputFormat.RTF,  
            "message/rfc822": InputFormat.EML,  
        }  
        if detected in mime\_map:  
            return mime\_map\[detected\]

    raise ValueError(f"Unsupported format: {file\_path or mime\_type}")

def ingest(file\_path: Path | None \= None, text: str | None \= None,  
           format\_hint: InputFormat | None \= None) \-\> list\[TextElement\]:  
    """  
    Main entry point. Detect format, extract, normalize, return elements.  
    """  
    if text and not file\_path:  
        fmt \= InputFormat.PASTE  
    elif format\_hint:  
        fmt \= format\_hint  
    else:  
        fmt \= detect\_format(file\_path, None)

    \# Dispatch to format-specific extractor  
    extractors \= {  
        InputFormat.PDF: extract\_pdf,  
        InputFormat.DOCX: extract\_docx,  
        InputFormat.DOC: extract\_doc,  
        InputFormat.MARKDOWN: extract\_markdown,  
        InputFormat.PLAIN\_TEXT: extract\_text,  
        InputFormat.HTML: extract\_html,  
        InputFormat.RTF: extract\_rtf,  
        InputFormat.EML: extract\_eml,  
        InputFormat.MSG: extract\_msg,  
        InputFormat.PASTE: extract\_paste,  
    }

    extractor \= extractors\[fmt\]  
    raw\_elements \= extractor(file\_path=file\_path, text=text)

    \# Apply format-aware normalization  
    normalized \= normalize\_elements(raw\_elements, fmt)

    return normalized

#### **6.1.3 Format-Specific Extractors**

Each extractor converts its source format into a list of `TextElement` objects. The extractor's job: preserve structural semantics (headings, paragraphs, tables, lists) while stripping format-specific artifacts (markup, styles, metadata). Each extractor lives in its own file under `backend/app/services/ingestion/`.

**SectionTracker** (shared utility used by DOCX, Markdown, and HTML extractors):

\# backend/app/services/ingestion/section\_tracker.py

class SectionTracker:
    """
    Tracks the current section hierarchy as headings are encountered.
    Produces section paths like "Article II > §2.3(a)" for provenance.

    Usage:
      tracker \= SectionTracker()
      tracker.update("Article II", level=1)
      tracker.update("§2.3 Rent Provisions", level=2)
      tracker.current\_path()  \# "Article II > §2.3 Rent Provisions"
      tracker.update("(a) Base Rent", level=3)
      tracker.current\_path()  \# "Article II > §2.3 Rent Provisions > (a) Base Rent"
      tracker.update("Article III", level=1)  \# resets deeper levels
      tracker.current\_path()  \# "Article III"
    """

    def \_\_init\_\_(self):
        self.\_stack: list\[tuple\[int, str\]\] \= \[\]  \# \[(level, heading\_text), ...\]

    def update(self, heading\_text: str, level: int) \-\> None:
        """Register a new heading. Pops any headings at the same or deeper level."""
        \# Remove headings at same or deeper level
        while self.\_stack and self.\_stack\[-1\]\[0\] \>= level:
            self.\_stack.pop()
        self.\_stack.append((level, heading\_text.strip()))

    def current\_path(self) \-\> str | None:
        """Return the current section path as a ' > '-joined string."""
        if not self.\_stack:
            return None
        return " > ".join(text for \_, text in self.\_stack)

**PDF** (`pdf_extractor.py`):

def extract\_pdf(file\_path: Path, \*\*kwargs) \-\> list\[TextElement\]:  
    """  
    Use Docling for structural extraction.  
    Docling detects: sections, headings, paragraphs, tables,  
    lists, headers/footers, page numbers.  
      
    FOLIO Mapper cross-reference: None — Docling is new to this pipeline.  
    """  
    from docling.document\_converter import DocumentConverter

    converter \= DocumentConverter()  
    result \= converter.convert(str(file\_path))

    elements \= \[\]  
    for i, item in enumerate(result.document.iterate\_items()):  
        elements.append(TextElement(  
            id=f"pdf\_{i}",  
            text=item.text,  
            element\_type=map\_docling\_label(item.label),  
            section\_path=extract\_section\_path(item),  
            page=item.prov\[0\].page if item.prov else None,  
            level=item.level if hasattr(item, "level") else None,  
            source\_format=InputFormat.PDF,  
        ))  
    return elements

**Microsoft Word** (`docx_extractor.py`):

def extract\_docx(file\_path: Path, \*\*kwargs) \-\> list\[TextElement\]:  
    """  
    Use python-docx to extract paragraphs, headings, and tables.  
    Word documents store semantic paragraphs — no soft-wrap problem.  
    Each paragraph becomes one TextElement.  
    Tables: each cell becomes a TextElement with element\_type="table\_cell".  
    """  
    from docx import Document

    doc \= Document(str(file\_path))  
    elements \= \[\]  
    section\_tracker \= SectionTracker()

    for i, para in enumerate(doc.paragraphs):  
        if not para.text.strip():  
            continue

        style\_name \= para.style.name.lower() if para.style else ""  
        if "heading" in style\_name:  
            level \= int(style\_name.replace("heading ", "")) if \\  
                style\_name.replace("heading ", "").isdigit() else 1  
            elem\_type \= "heading"  
            section\_tracker.update(para.text, level)  
        else:  
            level \= None  
            elem\_type \= "paragraph"

        elements.append(TextElement(  
            id=f"docx\_{i}",  
            text=para.text,  
            element\_type=elem\_type,  
            section\_path=section\_tracker.current\_path(),  
            page=None,  \# python-docx doesn't track page numbers  
            level=level,  
            source\_format=InputFormat.DOCX,  
        ))

    \# Extract tables  
    for t\_idx, table in enumerate(doc.tables):  
        for r\_idx, row in enumerate(table.rows):  
            for c\_idx, cell in enumerate(row.cells):  
                if cell.text.strip():  
                    elements.append(TextElement(  
                        id=f"docx\_table\_{t\_idx}\_{r\_idx}\_{c\_idx}",  
                        text=cell.text,  
                        element\_type="table\_cell",  
                        section\_path=section\_tracker.current\_path(),  
                        page=None,  
                        level=None,  
                        source\_format=InputFormat.DOCX,  
                    ))

    return elements

**Markdown** (`markdown_extractor.py`):

def extract\_markdown(file\_path: Path, \*\*kwargs) \-\> list\[TextElement\]:  
    """  
    Parse Markdown into structural elements.  
    Headings (\#, \#\#, \#\#\#) → heading elements with level.  
    Paragraphs → paragraph elements.  
    Code blocks → code\_block elements (preserved verbatim).  
    Lists → list\_item elements.  
    Blockquotes → blockquote elements.  
    """  
    from markdown\_it import MarkdownIt

    md \= MarkdownIt()  
    text \= file\_path.read\_text(encoding="utf-8")  
    tokens \= md.parse(text)

    elements \= \[\]  
    section\_tracker \= SectionTracker()

    for i, token in enumerate(tokens):  
        if token.type \== "heading\_open":  
            level \= int(token.tag\[1\])  \# h1 → 1, h2 → 2, etc.  
            \# Next token contains the heading text  
            continue  
        elif token.type \== "inline" and i \> 0 and \\  
                tokens\[i-1\].type \== "heading\_open":  
            level \= int(tokens\[i-1\].tag\[1\])  
            section\_tracker.update(token.content, level)  
            elements.append(TextElement(  
                id=f"md\_{i}",  
                text=token.content,  
                element\_type="heading",  
                section\_path=section\_tracker.current\_path(),  
                page=None, level=level,  
                source\_format=InputFormat.MARKDOWN,  
            ))  
        elif token.type \== "inline":  
            elements.append(TextElement(  
                id=f"md\_{i}",  
                text=token.content,  
                element\_type="paragraph",  
                section\_path=section\_tracker.current\_path(),  
                page=None, level=None,  
                source\_format=InputFormat.MARKDOWN,  
            ))  
        elif token.type \== "fence":  \# code blocks  
            elements.append(TextElement(  
                id=f"md\_{i}",  
                text=token.content,  
                element\_type="code\_block",  
                section\_path=section\_tracker.current\_path(),  
                page=None, level=None,  
                source\_format=InputFormat.MARKDOWN,  
            ))

    return elements

**HTML** (`html_extractor.py`):

def extract\_html(file\_path: Path \= None, text: str \= None,
                 \*\*kwargs) \-\> list\[TextElement\]:
    """
    Strip HTML tags, detect structural elements (h1–h6, p, li, table, pre).
    Collapse excessive whitespace. Decode HTML entities.
    Common source: court opinions scraped from public websites,
    regulatory filings, web-published legal commentary.
    Accepts either a file\_path or raw HTML text string (for email body reuse).
    """
    from bs4 import BeautifulSoup

    html \= text or file\_path.read\_text(encoding="utf-8", errors="replace")
    soup \= BeautifulSoup(html, "html.parser")

    \# Remove script, style, nav, footer, header elements  
    for tag in soup.find\_all(\["script", "style", "nav", "footer",  
                              "header", "aside"\]):  
        tag.decompose()

    elements \= \[\]  
    section\_tracker \= SectionTracker()

    for i, tag in enumerate(soup.find\_all(  
        \["h1", "h2", "h3", "h4", "h5", "h6",  
         "p", "li", "td", "th", "pre", "blockquote"\]  
    )):  
        text \= tag.get\_text(separator=" ", strip=True)  
        if not text:  
            continue

        tag\_name \= tag.name  
        if tag\_name.startswith("h") and len(tag\_name) \== 2:  
            level \= int(tag\_name\[1\])  
            section\_tracker.update(text, level)  
            elem\_type \= "heading"  
        elif tag\_name \== "li":  
            level, elem\_type \= None, "list\_item"  
        elif tag\_name in ("td", "th"):  
            level, elem\_type \= None, "table\_cell"  
        elif tag\_name \== "pre":  
            level, elem\_type \= None, "code\_block"  
        elif tag\_name \== "blockquote":  
            level, elem\_type \= None, "blockquote"  
        else:  
            level, elem\_type \= None, "paragraph"

        elements.append(TextElement(  
            id=f"html\_{i}", text=text,  
            element\_type=elem\_type,  
            section\_path=section\_tracker.current\_path(),  
            page=None, level=level,  
            source\_format=InputFormat.HTML,  
        ))

    return elements

**Plain text** (`text_extractor.py`):

def extract\_text(file\_path: Path \= None, text: str \= None,  
                 \*\*kwargs) \-\> list\[TextElement\]:  
    """  
    Split on blank lines to detect paragraphs.  
    No structural hierarchy available — all elements are paragraphs.  
    """  
    raw \= text or file\_path.read\_text(encoding="utf-8", errors="replace")  
    paragraphs \= re.split(r'\\n\\s\*\\n', raw)

    elements \= \[\]  
    for i, para in enumerate(paragraphs):  
        stripped \= para.strip()  
        if not stripped:  
            continue  
        elements.append(TextElement(  
            id=f"txt\_{i}", text=stripped,  
            element\_type="paragraph",  
            section\_path=None, page=None, level=None,  
            source\_format=InputFormat.PLAIN\_TEXT,  
        ))  
    return elements

**RTF** (`rtf_extractor.py`):

def extract\_rtf(file\_path: Path, \*\*kwargs) \-\> list\[TextElement\]:  
    """  
    Convert RTF to plain text via striprtf2, then treat as plain text.  
    RTF is common in older legal document management systems.  
    """  
    from striprtf.striprtf import rtf\_to\_text

    rtf\_content \= file\_path.read\_text(encoding="utf-8", errors="replace")  
    plain \= rtf\_to\_text(rtf\_content)  
    return extract\_text(text=plain)

**Email** (`email_extractor.py`):

def extract\_eml(file\_path: Path, \*\*kwargs) \-\> list\[TextElement\]:  
    """  
    Extract email body. Prefer HTML part (→ run through HTML extractor)  
    over plain text part. Include Subject as a heading element.  
    Strip signature blocks and legal disclaimers below "---" or  
    "CONFIDENTIALITY NOTICE" markers.  
    """  
    import email  
    from email import policy

    msg \= email.message\_from\_bytes(  
        file\_path.read\_bytes(), policy=policy.default  
    )

    elements \= \[\]

    \# Subject becomes heading  
    subject \= msg.get("Subject", "")  
    if subject:  
        elements.append(TextElement(  
            id="eml\_subject", text=subject,  
            element\_type="heading",  
            section\_path=None, page=None, level=1,  
            source\_format=InputFormat.EML,  
        ))

    \# Body extraction: prefer HTML, fallback to plain text  
    body \= msg.get\_body(preferencelist=("html", "plain"))  
    if body:  
        content\_type \= body.get\_content\_type()  
        content \= body.get\_content()

        if content\_type \== "text/html":
            \# Parse HTML body directly using BeautifulSoup
            \# (reuses the same logic as extract\_html, but from a string)
            body\_elements \= extract\_html(text=content)  
        else:  
            body\_elements \= extract\_text(text=content)

        \# Strip signatures and disclaimers  
        body\_elements \= strip\_email\_boilerplate(body\_elements)  
        elements.extend(body\_elements)

    return elements

**Pasted text** (`paste_handler.py`):

def extract\_paste(text: str \= None, \*\*kwargs) \-\> list\[TextElement\]:  
    """  
    User pastes text directly into the UI or API.  
    Treat identically to plain text extraction.  
      
    FOLIO Mapper cross-reference:  
      FOLIO Mapper's TextInput component (packages/ui/src/components/input/)  
      already handles pasted text for taxonomy mapping. The annotation  
      pipeline reuses the same UX pattern.  
    """  
    return extract\_text(text=text)

#### **6.1.4 Format-Aware Normalization**

Different formats produce different kinds of text artifacts. The normalizer calibrates its aggressiveness based on the source format:

\# backend/app/services/ingestion/normalizer.py

class NormalizationSeverity(Enum):  
    AGGRESSIVE \= "aggressive"   \# PDF: soft-wrap repair, dehyphenation, page-break repair  
    MODERATE \= "moderate"       \# HTML, RTF: whitespace collapse, entity decode  
    LIGHT \= "light"             \# Word, plain text, email: stray \\r\\n only  
    MINIMAL \= "minimal"         \# Markdown, paste: \\r\\n → \\n only

SEVERITY\_MAP \= {  
    InputFormat.PDF: NormalizationSeverity.AGGRESSIVE,  
    InputFormat.DOCX: NormalizationSeverity.LIGHT,  
    InputFormat.DOC: NormalizationSeverity.LIGHT,  
    InputFormat.MARKDOWN: NormalizationSeverity.MINIMAL,  
    InputFormat.PLAIN\_TEXT: NormalizationSeverity.LIGHT,  
    InputFormat.HTML: NormalizationSeverity.MODERATE,  
    InputFormat.RTF: NormalizationSeverity.MODERATE,  
    InputFormat.EML: NormalizationSeverity.LIGHT,  
    InputFormat.MSG: NormalizationSeverity.LIGHT,  
    InputFormat.PASTE: NormalizationSeverity.MINIMAL,  
}

def normalize\_elements(elements: list\[TextElement\],  
                       fmt: InputFormat) \-\> list\[TextElement\]:  
    severity \= SEVERITY\_MAP\[fmt\]

    normalized \= \[\]  
    for elem in elements:  
        text \= elem.text

        \# ALL formats: normalize \\r\\n → \\n  
        text \= text.replace("\\r\\n", "\\n").replace("\\r", "\\n")

        if severity \== NormalizationSeverity.AGGRESSIVE:  
            \# PDF-specific: full soft-wrap repair \+ dehyphenation  
            text \= normalize\_line\_breaks\_aggressive(text)

        elif severity \== NormalizationSeverity.MODERATE:  
            \# HTML/RTF: collapse excessive whitespace, strip stray tags  
            text \= collapse\_whitespace(text)

        elif severity \== NormalizationSeverity.LIGHT:  
            \# Word/text/email: trim trailing whitespace per line  
            text \= "\\n".join(line.rstrip() for line in text.split("\\n"))

        \# MINIMAL: no further processing beyond \\r\\n normalization

        normalized.append(TextElement(  
            id=elem.id,  
            text=text.strip(),  
            element\_type=elem.element\_type,  
            section\_path=elem.section\_path,  
            page=elem.page,  
            level=elem.level,  
            source\_format=elem.source\_format,  
        ))

    return \[e for e in normalized if e.text\]  \# drop empties

#### **6.1.5 The PDF Line-Break Problem (Aggressive Normalization)**

PDFs store text as individually positioned characters on a canvas — no semantic concept of "paragraph" or "sentence." When PDF renderers wrap text to fit a column width, they insert **visual line breaks** that carry no semantic meaning. Text extraction tools faithfully reproduce these breaks as `\n` characters, splitting multi-word concepts across lines:

Raw PDF extraction:  
    "The Tenant shall not commit any breach of\\n  
    contract or violation of the lease terms..."

What the author meant:  
    "The Tenant shall not commit any breach of contract  
    or violation of the lease terms..."

If the pipeline preserves every `\n` as a real paragraph break, "breach of contract" fragments into "breach of" at one line's end and "contract" at the next line's start. The LLM would never identify the full concept. Worse, deterministic string matching for "breach of contract" would fail because a newline sits in the middle.

A second variant involves **soft hyphens**: the PDF renderer hyphenates a word at a line break ("indemni-\\nfication"), producing "indemni-\\nfication" instead of "indemnification."

**This problem rarely affects other formats.** Word documents store semantic paragraphs. Markdown uses intentional line breaks. HTML collapses whitespace by design. Only PDFs (and occasionally RTF files exported from older systems) suffer from pervasive artificial line breaks.

#### **6.1.6 Line-Break Classification (PDF \+ RTF)**

Every `\n` in raw extracted text falls into one of three categories:

| Category | Signal | Action |
| ----- | ----- | ----- |
| **Real paragraph break** | Double newline (`\n\n`), or single `\n` preceded by sentence-ending punctuation (`.` `?` `!` followed optionally by `)` `]` `"` `'`) | **Preserve** as `\n` in canonical text |
| **Artificial line break** (soft wrap) | Single `\n` where the preceding line does NOT end with sentence-ending punctuation | **Replace with a space** — rejoin the wrapped text |
| **Hyphenated line break** | Line ends with a hyphen followed by `\n`, and the joined word (without hyphen) exists in a dictionary or FOLIO label set | **Remove hyphen and newline** — rejoin the word |

#### **6.1.7 Aggressive Normalization Algorithm**

import re  
import nltk  
from nltk.corpus import words as nltk\_words

\# Build a lookup set: English dictionary \+ all FOLIO concept labels  
word\_set \= set(w.lower() for w in nltk\_words.words())  
folio\_labels \= load\_folio\_labels()  \# all labels \+ alt labels from folio-python  
word\_set.update(w.lower() for w in folio\_labels)

SENTENCE\_END\_PATTERN \= re.compile(  
    r'\[.\!?\]\[\\"\\'\\)\\\]\\}\]?\\s\*$'  
)

def normalize\_line\_breaks\_aggressive(raw\_text: str) \-\> str:  
    """  
    Full soft-wrap repair \+ dehyphenation.  
    Apply ONLY to PDF and RTF sources. Other formats skip this entirely.  
    """  
    text \= raw\_text

    \# Preserve double newlines (paragraph breaks)  
    PARA\_PLACEHOLDER \= "\<\<\<PARA\>\>\>"  
    text \= re.sub(r'\\n\\s\*\\n', PARA\_PLACEHOLDER, text)

    \# Process remaining single newlines  
    lines \= text.split("\\n")  
    result\_parts \= \[\]

    for i, line in enumerate(lines):  
        stripped \= line.rstrip()  
        result\_parts.append(stripped)

        if i \< len(lines) \- 1:  
            next\_line \= lines\[i \+ 1\].lstrip()

            if stripped.endswith("-") and not stripped.endswith("--"):  
                \# Hyphenated line break: attempt dehyphenation  
                word\_prefix \= stripped.rsplit(None, 1)\[-1\]\[:-1\]  
                next\_word \= next\_line.split(None, 1)\[0\] if next\_line else ""  
                joined \= (word\_prefix \+ next\_word).lower()

                if joined in word\_set:  
                    \# Dehyphenate: remove hyphen, join directly  
                    result\_parts\[-1\] \= stripped\[:-1\]  
                else:  
                    \# Intentional hyphen (e.g., "non-compete")  
                    result\_parts.append(" ")

            elif SENTENCE\_END\_PATTERN.search(stripped):  
                \# Sentence-ending punctuation: real break  
                result\_parts.append("\\n")

            else:  
                \# Artificial soft wrap: replace with space  
                result\_parts.append(" ")

    \# Restore paragraph breaks  
    normalized \= "".join(result\_parts)  
    normalized \= normalized.replace(PARA\_PLACEHOLDER, "\\n\\n")

    return normalized

def collapse\_whitespace(text: str) \-\> str:  
    """  
    Moderate normalization for HTML/RTF.  
    Collapse runs of whitespace (spaces, tabs, newlines) into single spaces.  
    Preserve paragraph breaks (double newlines).  
    """  
    \# Preserve explicit paragraph breaks  
    text \= re.sub(r'\\n\\s\*\\n', '\\n\\n', text)  
    \# Collapse single newlines and runs of spaces into one space  
    text \= re.sub(r'(?\<\!\\n)\\n(?\!\\n)', ' ', text)  
    text \= re.sub(r'\[ \\t\]+', ' ', text)  
    return text

#### **6.1.8 Why Specific Formats Need Specific Extractors**

| Format | Why a Generic Text Extractor Falls Short |
| ----- | ----- |
| **PDF** | Characters stored as canvas coordinates — no paragraph boundaries, no reading order. Docling uses vision models to reconstruct structure. |
| **Word (.docx)** | Paragraphs and styles stored in XML. A generic text extractor loses heading levels, table structure, and style-based semantics (e.g., "Heading 2" \= section boundary). |
| **HTML** | Tags carry structure (`<h2>`, `<table>`, `<li>`). Stripping tags without interpreting them loses the structural hierarchy. |
| **Email** | MIME multipart encoding wraps the actual body. Headers, signatures, and legal disclaimers pollute the text if not filtered. |
| **Markdown** | `#`, `##`, `###` markers encode heading hierarchy. Code blocks (\`\`\` fences) should be preserved verbatim, not annotated for legal concepts. |
| **RTF** | Control words (`\par`, `\b`, `\i`) encode formatting. Raw extraction includes these as text garbage. |
| **Plain text / Paste** | No markup to parse — but paragraph detection from blank lines still matters for chunking boundaries. |

#### **6.1.9 Validation: Spot-Check Report**

After normalization, the pipeline generates a spot-check report listing format-specific corrections. The report adapts its content to the source format:

**PDF spot-check entries:**

\[  
  {  
    "rejoin\_type": "soft\_wrap",  
    "page": 14,  
    "before\_end": "...breach of",  
    "after\_start": "contract or violation...",  
    "joined\_result": "...breach of contract or violation..."  
  },  
  {  
    "rejoin\_type": "dehyphenation",  
    "page": 22,  
    "before\_end": "...indemni-",  
    "after\_start": "fication obligations...",  
    "joined\_result": "...indemnification obligations..."  
  }  
\]

**HTML spot-check entries:**

\[  
  {  
    "correction\_type": "tag\_stripped",  
    "original": "\<strong\>force majeure\</strong\> clause",  
    "result": "force majeure clause"  
  },  
  {  
    "correction\_type": "whitespace\_collapsed",  
    "original": "breach   of    contract",  
    "result": "breach of contract"  
  }  
\]

**Word/Markdown/Text:** Spot-check report typically empty — these formats produce clean text with minimal corrections needed.

---

### **6.2 Stage 2: Canonical Text Assembly \+ Freeze**

#### **6.2.1 Requirements**

1. Assemble all normalized `TextElement` objects (from any extractor) into a single string  
2. Record each element's `start_char` and `end_char` in the assembled string  
3. Store structural metadata (section path, page number, element type, source format) per offset range  
4. Compute a SHA-256 hash of the canonical text for integrity verification  
5. **Freeze the canonical text.** No downstream process may modify this string.

#### **6.2.2 Implementation**

import hashlib

def assemble\_canonical(elements: list\[TextElement\]) \-\> tuple:  
    """  
    Assemble normalized TextElements into a single canonical string.  
    Format-agnostic — works identically whether elements came from  
    PDF, Word, Markdown, HTML, paste, or any other extractor.  
    """  
    canonical\_parts \= \[\]  
    offset\_map \= \[\]  
    cursor \= 0

    for elem in elements:  
        canonical\_parts.append(elem.text)  
        offset\_map.append({  
            "element\_id": elem.id,  
            "start\_char": cursor,  
            "end\_char": cursor \+ len(elem.text),  
            "section\_path": elem.section\_path,  
            "page": elem.page,  
            "element\_type": elem.element\_type,  
            "source\_format": elem.source\_format.value,  
        })  
        cursor \+= len(elem.text) \+ 1  \# \+1 for newline separator

    canonical\_text \= "\\n".join(canonical\_parts)  
    text\_hash \= hashlib.sha256(canonical\_text.encode("utf-8")).hexdigest()

    return canonical\_text, offset\_map, text\_hash

#### **6.2.3 Invariant**

After this stage, the following must hold for the pipeline's entire remaining execution:

canonical\_text\[offset\_map\[i\]\["start\_char"\] : offset\_map\[i\]\["end\_char"\]\]  
    \== normalized text of element i

If this invariant breaks at any point, the pipeline halts and reports the failure.

---

### **6.2M Document Metadata Extraction**

Legal tech companies, law firms, and in-house legal departments need structured document metadata — document type, court, judge, parties, case number, dates — alongside concept annotations. Without metadata, annotations are orphaned: "Landlord" was found at position 45, but *in which document type, from which court, for which parties?*

FOLIO already defines the vocabulary for this metadata. Document Artifacts contains document types. Actors contains parties, judges, attorneys. Governmental Bodies contains courts. Locations contains jurisdictions. The pipeline already annotates these concepts in the document body. The metadata extraction layer *promotes* certain annotations from "concept found in text" to "document-level metadata field" and uses a Metadata Judge to classify the document itself.

#### **6.2M.1 Three Extraction Phases**

| Phase | When It Runs | What It Extracts | Method | LLM Calls |
| ----- | ----- | ----- | ----- | ----- |
| **Phase 1: Document Type** | After first 2–3 chunks available | Primary document type (FOLIO Document Artifacts taxonomy), attachments, caption fields | Metadata Judge reads opening text | 1 call, \~3K–6K tokens |
| **Phase 2: Structured Fields** | After targeted sections identified by Stage 3 chunker | Signatories, attorneys, governing law, venue, dates, claim types, relief, outcome | Metadata Judge reads targeted sections | 2–4 calls, \~2K–4K tokens each |
| **Phase 3: Annotation Promotion** | After Stages 1–6.75 complete | Promotes body annotations to metadata based on structural position | Deterministic — no LLM | 0 calls |

#### **6.2M.2 Phase 1 — Document Type Classification**

The Metadata Judge classifies the document type using two signals: the **filename** (if available) and the **opening text** (title, caption, header, introductory paragraph).

**Filename as classification signal.** The filename often contains the strongest hint about document type — but in unpredictable formats. Legal professionals use inconsistent naming conventions: `Motion_to_Dismiss.pdf`, `motiontodismiss.pdf`, `MTD.pdf`, `mtd_12b6_final_v3.pdf`, `2025-03-15_Def_MTD_SDNY.pdf`, `brief in support.docx`, `MSJ_opp_brief_FINAL.pdf`. Before calling the LLM, the pipeline runs a deterministic pre-classifier that normalizes the filename and matches against known abbreviations:

\# backend/app/services/metadata\_extractor.py

FILENAME\_ABBREVIATIONS \= {  
    \# Litigation  
    "mtd": "Motion to Dismiss",  
    "msj": "Motion for Summary Judgment",  
    "sj": "Summary Judgment",  
    "msl": "Motion to Strike",  
    "mtc": "Motion to Compel",  
    "osc": "Order to Show Cause",  
    "tro": "Temporary Restraining Order",  
    "pi": "Preliminary Injunction",  
    "rogs": "Interrogatories",  
    "rfp": "Request for Production",  
    "rfa": "Request for Admission",  
    "mtn": "Motion",  
    "opp": "Opposition",  
    "reply": "Reply Brief",  
    "memo": "Memorandum of Law",  
    "brief": "Brief",  
    "complaint": "Complaint",  
    "answer": "Answer",  
    "xc": "Cross-Complaint",  
    "cc": "Counterclaim",  
    "stip": "Stipulation",  
    "settle": "Settlement Agreement",  
    "depo": "Deposition Transcript",

    \# Contracts  
    "nda": "Non-Disclosure Agreement",  
    "msa": "Master Services Agreement",  
    "sow": "Statement of Work",  
    "apa": "Asset Purchase Agreement",  
    "spa": "Stock Purchase Agreement",  
    "loi": "Letter of Intent",  
    "psa": "Purchase and Sale Agreement",  
    "eula": "End User License Agreement",  
    "tos": "Terms of Service",

    \# Corporate  
    "aoi": "Articles of Incorporation",  
    "bylaws": "Bylaws",  
    "boa": "Board Resolution",  
    "proxy": "Proxy Statement",  
    "k10": "Annual Report (10-K)",  
    "10k": "Annual Report (10-K)",  
    "10q": "Quarterly Report (10-Q)",  
    "8k": "Current Report (8-K)",

    \# Other  
    "poa": "Power of Attorney",  
    "will": "Last Will and Testament",  
    "trust": "Trust Agreement",  
    "lease": "Lease Agreement",  
    "deed": "Deed",  
}

def classify\_filename(filename: str) \-\> dict | None:  
    """  
    Extract document type hints from the filename.  
      
    Handles: camelCase, snake\_case, concatenated words, abbreviations,  
    mixed case, version suffixes, date prefixes.  
      
    Returns a hint dict or None if no signal found.  
      
    Examples:  
      "motiontodismiss.pdf"        → "Motion to Dismiss"  
      "MTD.pdf"                    → "Motion to Dismiss"  
      "mtd\_12b6\_final\_v3.pdf"     → "Motion to Dismiss"  
      "NDA\_Acme\_Smith\_2025.docx"  → "Non-Disclosure Agreement"  
      "2025-03-15\_Def\_MSJ.pdf"    → "Motion for Summary Judgment"  
      "randomfile.pdf"             → None  
    """  
    if not filename:  
        return None

    \# Strip extension, lowercase, split on common separators  
    stem \= filename.rsplit(".", 1)\[0\].lower()  
    \# Split on underscores, hyphens, spaces, camelCase boundaries  
    import re  
    tokens \= re.split(r"\[\_\\-\\s\]+", stem)  
    \# Also split concatenated words: "motiontodismiss" → \["motion", "to", "dismiss"\]  
    expanded\_tokens \= \[\]  
    for token in tokens:  
        \# CamelCase split  
        parts \= re.sub(r"(\[a-z\])(\[A-Z\])", r"\\1 \\2", token).split()  
        expanded\_tokens.extend(parts)

    \# Check each token against abbreviation table  
    for token in expanded\_tokens:  
        if token in FILENAME\_ABBREVIATIONS:  
            return {  
                "hint": FILENAME\_ABBREVIATIONS\[token\],  
                "matched\_token": token,  
                "source": "filename\_abbreviation",  
            }

    \# Check multi-token phrases: "motion to dismiss" in joined tokens  
    joined \= " ".join(expanded\_tokens)  
    for abbrev, doc\_type in sorted(  
        FILENAME\_ABBREVIATIONS.items(), key=lambda x: len(x\[1\]), reverse=True  
    ):  
        if doc\_type.lower() in joined:  
            return {  
                "hint": doc\_type,  
                "matched\_token": doc\_type.lower(),  
                "source": "filename\_phrase",  
            }

    return None

The filename hint feeds into the Metadata Judge prompt as a prior signal — not a definitive classification. The filename might say `MTD.pdf` but the document might actually be a Reply Brief in support of a Motion to Dismiss. The Judge uses the filename hint to orient its analysis, then confirms or overrides based on the actual document text.

The Judge also classifies the document type against FOLIO's Document Artifacts taxonomy using the document's opening text. The opening text almost always declares the document's nature: "DEFENDANT'S MOTION TO DISMISS," "COMMERCIAL LEASE AGREEMENT," "OPINION AND ORDER."

The Judge distinguishes the primary document from its attachments. A Motion to Dismiss that attaches Exhibit A (the underlying contract) and Exhibit B (correspondence) is classified as "Motion to Dismiss" — not "Contract." The Judge identifies attachment boundaries (signaled by "EXHIBIT A," "APPENDIX 1," "SCHEDULE A") and classifies each attachment separately.

**Phase 1 Prompt:**

SYSTEM:  
You classify legal documents by type using the FOLIO Document Artifacts  
taxonomy. You analyze the document's filename and opening text — title,  
caption, header, and introductory paragraph — to determine:

1\. The PRIMARY document type (the document itself, not its attachments)  
2\. Any ATTACHMENTS with their own types (exhibits, schedules, appendices)  
3\. Structured metadata fields visible in the caption/header

The filename may contain abbreviations or concatenated words that hint  
at the document type (e.g., "mtd" \= Motion to Dismiss, "nda" \=  
Non-Disclosure Agreement). Use the filename as a prior signal, but  
ALWAYS confirm against the actual document text. The filename may be  
misleading — a file named "MTD.pdf" might contain a Reply Brief.

You must distinguish the document from its attachments. A Motion to  
Dismiss that attaches a contract is a "Motion to Dismiss," not a  
"Contract." Classify each separately.

FOLIO DOCUMENT TYPES (leaf-level concepts from Document Artifacts branch):  
{list of \~200 document type labels from FOLIO}

OUTPUT FORMAT (JSON):  
{  
  "document\_type": {  
    "folio\_label": "Motion to Dismiss",  
    "folio\_iri": "folio:DocArt\_MTD\_001",  
    "confidence": 0.95,  
    "evidence": "Title reads 'DEFENDANT'S MOTION TO DISMISS'; filename 'mtd\_12b6\_final.pdf' corroborates"  
  },  
  "document\_subtype": {  
    "folio\_label": "Motion to Dismiss for Failure to State a Claim",  
    "folio\_iri": "folio:DocArt\_MTD\_FRCP12b6\_001",  
    "confidence": 0.88,  
    "evidence": "References Rule 12(b)(6) in opening paragraph"  
  },  
  "attachments": \[  
    {  
      "label": "Exhibit A",  
      "document\_type": "Employment Agreement",  
      "folio\_iri": "folio:DocArt\_EmpAgmt\_001",  
      "boundary\_marker": "EXHIBIT A",  
      "approximate\_position": "page 12"  
    }  
  \],  
  "caption\_fields": {  
    "case\_number": "Case No. 1:2025-cv-01234-ABC",  
    "court": "United States District Court, Southern District of New York",  
    "judge": "Hon. Sarah Chen",  
    "parties": \[  
      {"name": "Acme Corp", "role": "Plaintiff"},  
      {"name": "John Smith", "role": "Defendant"}  
    \],  
    "filing\_date": "2025-03-15"  
  }  
}

USER:  
FILENAME: {original filename, e.g., "mtd\_12b6\_final\_v3.pdf"}  
FILENAME HINT: {result of classify\_filename(), e.g., "Motion to Dismiss" or "none"}

DOCUMENT OPENING TEXT (first \~3,000 tokens):  
"""  
{first 2-3 chunks of canonical text}  
"""

Classify this document and extract structured metadata.

#### **6.2M.3 Phase 2 — Structured Field Extraction**

Phase 2 targets specific structural locations where metadata fields live predictably. The pipeline uses section headers from Stage 1 extractors to find these regions — no full-document scan required:

| Metadata Fields | Where They Live | How Found |
| ----- | ----- | ----- |
| Case number, court, judge, parties | Caption / header | First 1–2 chunks; "v." pattern, "Case No." pattern |
| Signatories, attorneys | Signature block | Last 2–3 chunks; "By: \_\_\_", "/s/", "Respectfully submitted" |
| Governing law, venue | Boilerplate clauses (near end) | Section headers: "Governing Law," "Venue," "Choice of Law" |
| Effective date, termination date | Preamble or term clause | First 1–2 chunks; section header "Term," "Duration" |
| Claim types, relief sought | Causes of action, prayer for relief | Section headers: "Count I," "WHEREFORE" |
| Outcome (court opinions) | Holdings section | Section headers: "ORDER," "CONCLUSION," "HELD" |

**Phase 2 Prompt:**

SYSTEM:  
Extract structured metadata fields from a legal document section.  
You will receive a specific section (signature block, governing law  
clause, prayer for relief, or holdings) and extract the relevant fields.

DOCUMENT TYPE: {from Phase 1}

OUTPUT FORMAT (JSON — include only fields present in the section):  
{  
  "signatories": \[  
    {"name": "...", "title": "...", "party": "...",  
     "organization": "..."}  
  \],  
  "attorneys": \[  
    {"name": "...", "bar\_number": "...", "firm": "...",  
     "representing": "...", "contact": "..."}  
  \],  
  "governing\_law": {"jurisdiction": "...", "text": "..."},  
  "venue": {"forum": "...", "text": "..."},  
  "effective\_date": "YYYY-MM-DD",  
  "termination\_date": "YYYY-MM-DD",  
  "claim\_types": \[  
    {"claim": "...", "statute": "...", "count\_number": 1}  
  \],  
  "relief\_sought": \["..."\],  
  "outcome": {"disposition": "...", "text": "..."}  
}

USER:  
SECTION TYPE: {signature\_block | governing\_law | prayer\_for\_relief | holdings | preamble}  
TEXT:  
"""  
{targeted section text, \~500-2000 tokens}  
"""

Extract all metadata fields present in this section.

#### **6.2M.4 Phase 3 — Annotation Promotion**

After Stages 1–6.75 complete, the metadata extractor scans annotations and promotes those that carry document-level significance based on their structural position. No LLM calls — purely deterministic.

An "attorney" annotation in body text remains just an annotation. An "attorney" annotation in a signature block or appearance section becomes a metadata field.

\# backend/app/services/metadata\_extractor.py (NEW)

def promote\_annotations\_to\_metadata(
    annotations: list\[dict\],
    offset\_map: list\[dict\],
    canonical\_text: str,
    document\_metadata: dict,
) \-\> dict:
    """
    Scan annotations for concepts that carry document-level
    significance based on their structural position.
    """
    signature\_block\_range \= find\_section\_range(
        offset\_map, patterns=\["signature", "respectfully submitted",
                              "agreed and accepted"\],
        canonical\_text=canonical\_text,
    )
    governing\_law\_range \= find\_section\_range(
        offset\_map, patterns=\["governing law", "choice of law",
                              "applicable law"\],
        canonical\_text=canonical\_text,
    )
    claims\_range \= find\_section\_range(
        offset\_map, patterns=\["count", "cause of action",
                              "claim for relief"\],
        canonical\_text=canonical\_text,
    )
    holdings\_range \= find\_section\_range(
        offset\_map, patterns=\["order", "conclusion",
                              "it is hereby ordered", "held"\],
        canonical\_text=canonical\_text,  
    )

    promoted \= {}

    for ann in annotations:  
        pos \= ann\["start"\]  
        branch \= ann.get("branch", "")

        \# Signatories: Actor concepts in signature blocks  
        if branch \== "Actors" and in\_range(pos, signature\_block\_range):  
            promoted.setdefault("signatories", \[\]).append({  
                "name": ann\["text"\],  
                "folio\_iri": ann\["iri"\],  
                "folio\_label": ann\["label"\],  
                "position": pos,  
            })

        \# Governing law: Location/Jurisdiction concepts  
        if branch in ("Locations", "Governmental Bodies") \\  
                and in\_range(pos, governing\_law\_range):  
            promoted\["governing\_law"\] \= {  
                "text": ann\["text"\],  
                "folio\_iri": ann\["iri"\],  
                "folio\_label": ann\["label"\],  
            }

        \# Claim types: Area of Law concepts in claims sections  
        if branch \== "Area of Law" and in\_range(pos, claims\_range):  
            promoted.setdefault("claim\_types", \[\]).append({  
                "text": ann\["text"\],  
                "folio\_iri": ann\["iri"\],  
                "folio\_label": ann\["label"\],  
            })

        \# Outcome: Event concepts in holdings sections  
        if branch \== "Events" and in\_range(pos, holdings\_range):  
            promoted.setdefault("outcomes", \[\]).append({  
                "text": ann\["text"\],  
                "folio\_iri": ann\["iri"\],  
                "folio\_label": ann\["label"\],  
            })

    document\_metadata.update(promoted)  
    return document\_metadata

def find\_section\_range(
    offset\_map: list\[dict\],
    patterns: list\[str\],
    canonical\_text: str,
) \-\> tuple\[int, int\] | None:
    """
    Find the character range of a document section by matching
    section headers against known patterns.
    """
    for elem in offset\_map:
        section\_path \= (elem.get("section\_path") or "").lower()
        element\_type \= elem.get("element\_type", "")
        \# Look up element text from canonical string using offset map
        elem\_text \= canonical\_text\[elem\["start\_char"\]:elem\["end\_char"\]\]
        text\_lower \= elem\_text.lower()

        for pattern in patterns:  
            if pattern in section\_path or (  
                element\_type \== "heading" and pattern in text\_lower  
            ):  
                start \= elem\["start\_char"\]  
                end \= find\_next\_heading(offset\_map, start)  
                return (start, end)  
    return None

def in\_range(pos: int, section\_range: tuple | None) \-\> bool:  
    if section\_range is None:  
        return False  
    return section\_range\[0\] \<= pos \< section\_range\[1\]

#### **6.2M.5 Complete Metadata Fields**

| Category | Field | Source | FOLIO Branch |
| ----- | ----- | ----- | ----- |
| **Document Identity** | `document_type` | Phase 1 Judge | Document Artifacts |
|  | `document_subtype` | Phase 1 Judge | Document Artifacts |
|  | `attachments` (with types) | Phase 1 Judge | Document Artifacts |
| **Case Information** | `case_number` | Phase 1 caption | — |
|  | `docket_number` | Phase 1 caption | — |
|  | `case_caption` | Phase 1 caption | — |
|  | `filing_date` | Phase 1 caption | — |
|  | `document_date` | Phase 1 caption / Phase 2 preamble | — |
| **Court** | `court` (name, level, district) | Phase 1 caption | Governmental Bodies |
|  | `jurisdiction_type` (federal/state) | Derived from court | Governmental Bodies |
|  | `panel` (appellate opinions) | Phase 2 holdings | Actors |
| **People** | `judge` | Phase 1 caption | Actors |
|  | `parties` (name, role, type, counsel) | Phase 1 caption \+ Phase 2 sig block | Actors |
|  | `attorneys` (name, bar\#, firm, representing) | Phase 2 signature block | Actors |
|  | `signatories` (name, title, org) | Phase 3 annotation promotion | Actors |
|  | `witnesses` | Phase 2 witness list (depositions) | Actors |
| **Contract Terms** | `effective_date` | Phase 2 preamble | Engagement Terms |
|  | `termination_date` | Phase 2 term clause | Engagement Terms |
|  | `governing_law` | Phase 2 / Phase 3 promotion | Locations |
|  | `venue` | Phase 2 / Phase 3 promotion | Governmental Bodies |
| **Litigation** | `claim_types` (with statutes) | Phase 2 / Phase 3 promotion | Area of Law |
|  | `relief_sought` | Phase 2 prayer for relief | Events |
|  | `outcome` (disposition, details) | Phase 2 holdings / Phase 3 | Events |
| **Concept Summary** | `annotations_by_branch` | Post-pipeline aggregation | — |
|  | `top_concepts` (top 10 with counts) | Post-pipeline aggregation | — |
|  | `top_cooccurrence_pairs` | Post-pipeline aggregation | — |
|  | `top_triples` | Post-pipeline aggregation | — |

#### **6.2M.6 Token Economics**

| Phase | Input Tokens | Output Tokens | LLM Calls | Total Tokens |
| ----- | ----- | ----- | ----- | ----- |
| Phase 1: Document type \+ caption | \~3,000–6,000 | \~500 | 1 | \~3,500–6,500 |
| Phase 2: Signature block | \~1,000–2,000 | \~300 | 1 | \~1,300–2,300 |
| Phase 2: Governing law / venue | \~500–1,000 | \~200 | 1 | \~700–1,200 |
| Phase 2: Claims / relief (if litigation) | \~1,000–2,000 | \~300 | 0–1 | \~0–2,300 |
| Phase 2: Holdings / outcome (if opinion) | \~1,000–2,000 | \~200 | 0–1 | \~0–2,200 |
| Phase 3: Annotation promotion | 0 | 0 | 0 | 0 (deterministic) |
| **Total per document** |  |  | **3–5 calls** | **\~5,500–14,500 tokens** |

Metadata extraction adds \~5K–15K tokens — roughly 3–10% of Stage 4's cost. Modest investment for structured metadata that transforms exports from "bag of annotations" into "indexed legal intelligence."

#### **6.2M.7 Progressive Rendering of Metadata**

Phase 1 completes early (after first 2–3 chunks, before the LLM pipeline finishes). The document type and caption fields stream to the frontend via SSE:

event: document\_metadata  
data: {  
  "phase": 1,  
  "document\_type": {"folio\_label": "Motion to Dismiss", ...},  
  "case\_number": "1:2025-cv-01234-ABC",  
  "court": "Southern District of New York",  
  "judge": "Hon. Sarah Chen",  
  "parties": \[...\]  
}

Phase 2 and Phase 3 results stream as they complete:

event: document\_metadata\_update  
data: {  
  "phase": 2,  
  "section": "signature\_block",  
  "attorneys": \[...\],  
  "signatories": \[...\]  
}

---

### **6.2A Dual-Path Split: EntityRuler ∥ LLM Pipeline**

After Stage 2 produces the canonical text, the pipeline splits into two parallel paths that run simultaneously with zero awareness of each other:

**Path A — EntityRuler (deterministic, fast):** Scans the full canonical text against all 18,000+ FOLIO labels using spaCy's EntityRuler. Completes in 2–3 seconds for a 500-page document. Results stream to the frontend immediately as "preliminary" annotations (high-specificity matches only).

**Path B — LLM Pipeline (contextual, slower):** Chunks the canonical text, submits chunks to the LLM for concept identification, and streams results per-chunk as the LLM completes each call.

Both paths feed into the Reconciliation Layer (Stage 4.5), which merges their outputs and uses an LLM Judge to resolve conflicts.

           Canonical Text (Stage 2\)  
                      │  
         ┌────────────┼────────────┐  
         │ (parallel)  │            │ (parallel)  
         ▼             │            ▼  
    ┌──────────┐       │    ┌──────────────┐  
    │ Path A:   │       │    │ Path B:       │  
    │ EntityRuler│       │    │ Stage 3 → 4  │  
    │ (\~2–3 sec)│       │    │ (chunking \+   │  
    │           │       │    │  LLM, minutes) │  
    └─────┬────┘       │    └──────┬───────┘  
          │            │           │  
          │  ┌─────────▼─────────┐ │  
          └─►│ Stage 4.5:        │◄┘  
             │ Reconciliation    │  
             │ Aligner \+ Judge   │  
             └─────────┬─────────┘  
                       │  
                       ▼  
              Merged Concept List  
              → Stage 5 (Resolution)

---

### **6.2B Path A: EntityRuler — Deterministic FOLIO Label Scan**

#### **6.2B.1 Purpose**

The EntityRuler scans the full canonical text against all 18,000+ FOLIO labels using spaCy's `EntityRuler` component. It finds every literal occurrence of a FOLIO concept in the document — including multi-word terms ("Breach of Contract," "Writ of Certiorari") and FOLIO verbs ("denied," "overruled," "drafted").

The EntityRuler has zero context sensitivity. It matches "Interest" in "pay Interest at 5%" (legal concept) and "no interest in attending" (common English) identically. The Reconciliation Layer (Stage 4.5) resolves these ambiguities using the LLM Judge.

#### **6.2B.2 Confidence Tiers**

Not all EntityRuler matches carry equal confidence. Multi-word legal terms almost certainly represent legal concepts. Common single words often do not. The EntityRuler classifies each match into a confidence tier:

| Tier | Criteria | Examples | Action |
| ----- | ----- | ----- | ----- |
| **High** | Multi-word FOLIO label (2+ words) | "Breach of Contract," "force majeure," "Writ of Certiorari" | Render immediately as "preliminary" annotation |
| **High** | Single-word label NOT in top-5000 common English words | "indemnification," "estoppel," "subrogation" | Render immediately as "preliminary" annotation |
| **Low** | Single-word label IN top-5000 common English words | "Interest," "Term," "Party," "Order," "Action" | Hold — do NOT render; await Reconciliation Judge |

The confidence tier is pre-computed once during EntityRuler initialization by cross-referencing FOLIO labels against a word-frequency list (e.g., NLTK's `words` corpus or a custom legal frequency list).

#### **6.2B.3 Implementation**

\# backend/app/services/entity\_ruler\_service.py (NEW)

import spacy  
from spacy.pipeline import EntityRuler  
from folio import FOLIO

def build\_entity\_ruler() \-\> tuple\[spacy.Language, dict\]:  
    """  
    Build a spaCy pipeline with EntityRuler loaded with all FOLIO labels.  
    Returns the pipeline and a label→metadata lookup dict.  
      
    Called once at pipeline startup. The spaCy pipeline is reused  
    across all documents.  
    """  
    nlp \= spacy.blank("en")  \# blank model — no NER, no parser, just tokenizer \+ ruler  
    ruler \= nlp.add\_pipe("entity\_ruler")

    folio \= FOLIO()  
    patterns \= \[\]  
    label\_metadata \= {}  
    common\_words \= load\_common\_word\_set()  \# top-5000 English words

    for concept in folio.get\_all\_classes():  
        label \= concept.label  
        iri \= concept.iri  
        words \= label.split()  
        is\_high\_confidence \= (  
            len(words) \>= 2  
            or label.lower() not in common\_words  
        )

        \# Create EntityRuler pattern  
        pattern\_tokens \= \[{"LOWER": w.lower()} for w in words\]  
        patterns.append({  
            "label": f"FOLIO\_{concept.branch}",  
            "pattern": pattern\_tokens,  
            "id": iri,  
        })

        label\_metadata\[label.lower()\] \= {  
            "iri": iri,  
            "label": label,  
            "branch": concept.branch,  
            "confidence\_tier": "high" if is\_high\_confidence else "low",  
        }

    ruler.add\_patterns(patterns)  
    return nlp, label\_metadata

async def run\_entity\_ruler(  
    canonical\_text: str,  
    nlp: spacy.Language,  
    label\_metadata: dict,  
) \-\> list\[dict\]:  
    """  
    Scan the full canonical text against all FOLIO labels.  
    Returns a list of matches with confidence tiers.  
      
    For a 500-page document (\~2.5M chars), runs in \~2–3 seconds.  
    """  
    doc \= nlp(canonical\_text)  
    matches \= \[\]

    for ent in doc.ents:  
        meta \= label\_metadata.get(ent.text.lower(), {})  
        matches.append({  
            "text": ent.text,  
            "start": ent.start\_char,  
            "end": ent.end\_char,  
            "folio\_label": meta.get("label", ent.text),  
            "folio\_iri": meta.get("iri"),  
            "branch": meta.get("branch"),  
            "confidence\_tier": meta.get("confidence\_tier", "low"),  
            "source": "entity\_ruler",  
        })

    return matches

#### **6.2B.4 Progressive Rendering of EntityRuler Results**

ALL EntityRuler matches stream to the frontend immediately via SSE — both high-confidence and low-confidence. The visual treatment communicates certainty level:

| Confidence Tier | Visual Treatment | Meaning |
| ----- | ----- | ----- |
| **High** (multi-word, legal-specific) | Solid highlight, branch-colored | Almost certainly a legal concept; awaiting LLM confirmation |
| **Low** (common English word matching FOLIO label) | Lighter highlight \+ uncertainty indicator (dotted border, "?" badge, or reduced opacity) | Might be a legal concept; system needs to verify from context |

event: preliminary\_annotations  
data: {  
  "source": "entity\_ruler",  
  "annotations": \[  
    {"text": "Breach of Contract", "start": 100, "end": 119,  
     "branch": "Litigation Claims", "confidence\_tier": "high"},  
    {"text": "force majeure", "start": 4500, "end": 4513,  
     "branch": "Contractual Clause", "confidence\_tier": "high"},  
    {"text": "Interest", "start": 120, "end": 128,  
     "confidence\_tier": "low"},  
    {"text": "Term", "start": 45, "end": 49,  
     "confidence\_tier": "low"}  
  \]  
}

Legal professionals prefer seeing false positives over missing real concepts. Showing all matches — with visual uncertainty signals — respects the user's expertise and lets them form their own judgment while the pipeline catches up. The user sees the system's full picture from the start, not a filtered subset.

A **"Hide uncertain" toggle** in the toolbar lets the user switch between "Show all" (default) and "Show confirmed only" for focused reading. The toggle state persists per session.

---

### **6.2C Path A Extension: Semantic EntityRuler — Synonym and Paraphrase Discovery**

#### **6.2C.1 Purpose**

The literal EntityRuler (§6.2B) matches FOLIO labels exactly: "Breach of Contract" matches "Breach of Contract." But legal documents use synonyms, abbreviations, and paraphrases constantly. "Contractual breach," "breach claim," "breach action" — none match any FOLIO label literally. The LLM catches some through contextual understanding, but the LLM takes minutes.

The Semantic EntityRuler extends Path A with embedding-based near-match discovery. It extracts noun phrases from the canonical text, embeds them, and compares against the pre-computed FOLIO label embedding index. Near-matches above a similarity threshold become candidate annotations.

#### **6.2C.2 Implementation**

The Semantic EntityRuler runs as a second phase of Path A, after the literal EntityRuler completes:

\# backend/app/services/semantic\_entity\_ruler.py (NEW)

import spacy  
from app.services.embedding\_service import EmbeddingService

async def run\_semantic\_entity\_ruler(  
    canonical\_text: str,  
    nlp: spacy.Language,  
    embedding\_service: EmbeddingService,  
    literal\_matches: set\[str\],  
    similarity\_threshold: float \= 0.82,  
    max\_results\_per\_phrase: int \= 3,  
) \-\> list\[dict\]:  
    """  
    Discover FOLIO concepts via embedding similarity for phrases  
    that the literal EntityRuler missed.  
      
    1\. Extract noun phrases from canonical text (spaCy noun chunker)  
    2\. Filter out phrases already matched by literal EntityRuler  
    3\. Embed remaining phrases  
    4\. Find nearest FOLIO labels via FAISS index  
    5\. Return near-matches above threshold  
      
    For a 500-page document: \~50K noun phrases, \~6–13 sec on CPU.  
    """  
    doc \= nlp(canonical\_text)

    \# Extract unique noun phrases not already matched literally  
    candidate\_phrases \= {}  
    for chunk in doc.noun\_chunks:  
        phrase \= chunk.text.strip()  
        phrase\_lower \= phrase.lower()  
        if (  
            len(phrase) \>= 3  
            and phrase\_lower not in literal\_matches  
            and not phrase\_lower.isdigit()  
        ):  
            if phrase\_lower not in candidate\_phrases:  
                candidate\_phrases\[phrase\_lower\] \= {  
                    "text": phrase,  
                    "occurrences": \[\],  
                }  
            candidate\_phrases\[phrase\_lower\]\["occurrences"\].append(  
                (chunk.start\_char, chunk.end\_char)  
            )

    if not candidate\_phrases:  
        return \[\]

    \# Batch embed all unique candidate phrases  
    phrases \= list(candidate\_phrases.keys())  
    phrase\_embeddings \= embedding\_service.embed\_batch(  
        \[candidate\_phrases\[p\]\["text"\] for p in phrases\]  
    )

    \# Find nearest FOLIO labels for each phrase  
    matches \= \[\]  
    for i, phrase in enumerate(phrases):  
        neighbors \= embedding\_service.nearest\_neighbors(  
            vector=phrase\_embeddings\[i\],  
            k=max\_results\_per\_phrase,  
        )  
        for iri, label, score, branch in neighbors:  
            if score \>= similarity\_threshold:  
                for start, end in candidate\_phrases\[phrase\]\["occurrences"\]:  
                    matches.append({  
                        "text": candidate\_phrases\[phrase\]\["text"\],  
                        "start": start,  
                        "end": end,  
                        "folio\_label": label,  
                        "folio\_iri": iri,  
                        "branch": branch,  
                        "confidence\_tier": "semantic",  
                        "similarity\_score": round(score, 3),  
                        "source": "semantic\_entity\_ruler",  
                    })

    return matches

#### **6.2C.3 Confidence Tier: Semantic**

Semantic matches introduce a fourth confidence tier alongside the existing three:

| Tier | Source | Visual Treatment | Example |
| ----- | ----- | ----- | ----- |
| **High** | EntityRuler exact match, multi-word or legal-specific | Solid highlight, branch-colored | "Breach of Contract," "indemnification" |
| **Low** | EntityRuler exact match, common English word | Lighter highlight \+ "?" badge | "Interest," "Term," "Party" |
| **Semantic** | Embedding near-match, no exact FOLIO label hit | Lighter highlight \+ "≈" badge | "contractual breach" ≈ "Breach of Contract" |
| **Contextual** | LLM-only discovery, no EntityRuler match at all | Standard confirmed highlight (arrives later) | "the agreement" → Contract |

Semantic matches flow into the Reconciliation Layer identically to low-confidence EntityRuler matches. The Reconciliation Judge evaluates them with the same prompt, noting the discovery source: "Semantic embedding matched 'contractual breach' to FOLIO label 'Breach of Contract' (similarity: 0.87). Does this phrase function as that legal concept in this context?"

#### **6.2C.4 Progressive Rendering Timeline (Updated)**

| Time | Event | Source |
| ----- | ----- | ----- |
| 0–1 sec | Document text appears | Ingestion |
| 2–3 sec | Exact EntityRuler matches (high \+ low confidence) | Literal EntityRuler |
| 6–13 sec | Semantic near-matches appear with "≈" badge | Semantic EntityRuler |
| 8–15 sec | First chunk LLM results \+ reconciliation | LLM \+ Reconciliation |
| 15–60 sec | Remaining chunks reconcile | LLM \+ Reconciliation |
| 1–5 min | Pipeline complete | All stages |

The Semantic EntityRuler results arrive between the literal EntityRuler and the first LLM chunk — filling a gap in the progressive rendering timeline where the user previously waited with no new annotations appearing.

---

### **6.2D Shared Embedding Service**

#### **6.2D.1 Architecture**

The `EmbeddingService` is a shared singleton that provides pre-computed FOLIO label embeddings and on-demand text embedding to every pipeline stage that needs semantic similarity:

┌─────────────────────────────────────────────────┐  
│  EmbeddingService (shared singleton)             │  
│                                                  │  
│  Pre-computed:                                   │  
│    FOLIO label embeddings (18K vectors, cached)  │  
│    FAISS index for nearest-neighbor search        │  
│                                                  │  
│  Methods:                                        │  
│    embed(text) → vector                          │  
│    embed\_batch(texts) → vectors                  │  
│    similarity(text, iri) → float                 │  
│    nearest\_neighbors(text/vector, k, branch)     │  
│        → \[(iri, label, score, branch)\]           │  
│                                                  │  
│  Consumers:                                      │  
│    §6.2C  Semantic EntityRuler                   │  
│    §6.4A  Reconciliation triage                  │  
│    §6.5   Resolution fallback                    │  
│    §6.7   Branch Judge triage                    │  
└─────────────────────────────────────────────────┘

#### **6.2D.2 Provider Abstraction**

The embedding service follows FOLIO Mapper's existing LLM provider-abstraction pattern (`backend/app/services/llm/`). Each provider implements the same interface; the user selects their preferred provider in configuration:

\# backend/app/services/embedding/\_\_init\_\_.py (NEW)

from abc import ABC, abstractmethod  
import numpy as np

class EmbeddingProvider(ABC):  
    """Abstract interface for embedding providers."""

    @abstractmethod  
    def embed(self, text: str) \-\> np.ndarray:  
        """Embed a single text string."""  
        ...

    @abstractmethod  
    def embed\_batch(self, texts: list\[str\]) \-\> np.ndarray:  
        """Embed multiple texts efficiently."""  
        ...

    @abstractmethod  
    def model\_name(self) \-\> str:  
        """Return the model identifier (used for cache key)."""  
        ...

    @abstractmethod  
    def dimensions(self) \-\> int:  
        """Return the embedding dimensionality."""  
        ...

**Available providers:**

| Provider | Models | Location | Cost | Legal Quality | Best For |
| ----- | ----- | ----- | ----- | ----- | ----- |
| **LocalProvider** (default) | `all-mpnet-base-v2` (768d), `all-MiniLM-L6-v2` (384d), `bge-large-en-v1.5` (1024d) | CPU/GPU, no network | $0.00 | Very good | Air-gapped environments, cost-sensitive deployments, default |
| **OllamaProvider** | `nomic-embed-text`, `mxbai-embed-large` | Local via Ollama API | $0.00 | Good | Users already running Ollama for LLM |
| **VoyageProvider** | `voyage-law-2` (1024d) | Cloud API | \~$0.12/1M tokens | **Best** (legal-domain trained) | Maximum legal accuracy |
| **OpenAIProvider** | `text-embedding-3-small` (1536d), `text-embedding-3-large` (3072d) | Cloud API | $0.02–0.13/1M tokens | Very good | Users already using OpenAI for LLM |
| **CohereProvider** | `embed-english-v3.0` (1024d) | Cloud API | \~$0.10/1M tokens | Good | Users already using Cohere |

\# backend/app/services/embedding/local\_provider.py (NEW)

from sentence\_transformers import SentenceTransformer  
import numpy as np

class LocalEmbeddingProvider(EmbeddingProvider):  
    """Local embedding via sentence-transformers. No network required."""

    def \_\_init\_\_(self, model\_name: str \= "all-mpnet-base-v2"):  
        self.\_model\_name \= model\_name  
        self.\_model \= SentenceTransformer(model\_name)

    def embed(self, text: str) \-\> np.ndarray:  
        return self.\_model.encode(text, normalize\_embeddings=True)

    def embed\_batch(self, texts: list\[str\]) \-\> np.ndarray:  
        return self.\_model.encode(  
            texts, normalize\_embeddings=True, batch\_size=256,  
            show\_progress\_bar=False,  
        )

    def model\_name(self) \-\> str:  
        return self.\_model\_name

    def dimensions(self) \-\> int:  
        return self.\_model.get\_sentence\_embedding\_dimension()

#### **6.2D.3 Configuration**

\# Environment variable or config file  
EMBEDDING\_PROVIDER=local              \# local | ollama | voyage | openai | cohere  
EMBEDDING\_MODEL=all-mpnet-base-v2     \# provider-specific model name  
EMBEDDING\_CACHE\_DIR=\~/.folio/cache    \# pre-computed FOLIO vectors

**Automatic fallback:** If the configured cloud provider is unreachable (no internet, API down, rate limited), the pipeline falls back to `LocalEmbeddingProvider` with `all-mpnet-base-v2` automatically. The pipeline logs a warning but continues without interruption:

WARNING: Voyage AI API unreachable — falling back to local  
         embedding model (all-mpnet-base-v2).  
         Semantic matching quality may decrease slightly.

#### **6.2D.4 FOLIO Embedding Cache**

Pre-computed FOLIO label embeddings cache to disk and rebuild only when the FOLIO OWL file updates:

\# backend/app/services/embedding/folio\_index.py (NEW)

import hashlib  
import numpy as np  
import faiss  
from pathlib import Path  
from folio import FOLIO

class FOLIOEmbeddingIndex:  
    """  
    Pre-computed FOLIO label embeddings with FAISS nearest-neighbor index.  
      
    Cache lifecycle:  
      1\. On startup, compute hash of FOLIO OWL file  
      2\. Check for cached embeddings at:  
         {cache\_dir}/folio\_embeddings\_{model\_name}\_{owl\_hash}.npz  
      3\. Cache hit → load from disk (\<1 second, \~28MB)  
      4\. Cache miss → re-embed all 18K labels (\~5–30 sec), save cache  
      
    Switching embedding models creates a new cache file without  
    destroying existing caches. Switching back hits the old cache.  
    """

    def \_\_init\_\_(  
        self,  
        provider: "EmbeddingProvider",  
        cache\_dir: str \= "\~/.folio/cache",  
    ):  
        self.provider \= provider  
        self.cache\_dir \= Path(cache\_dir).expanduser()  
        self.cache\_dir.mkdir(parents=True, exist\_ok=True)

        self.folio \= FOLIO()  
        self.owl\_hash \= self.\_compute\_owl\_hash()  
        self.cache\_path \= (  
            self.cache\_dir  
            / f"folio\_embeddings\_{provider.model\_name()}\_{self.owl\_hash\[:12\]}.npz"  
        )

        \# Load or build  
        if self.cache\_path.exists():  
            self.\_load\_cache()  
        else:  
            self.\_build\_and\_cache()

        \# Build FAISS index  
        self.\_build\_faiss\_index()

    def \_compute\_owl\_hash(self) \-\> str:  
        """SHA-256 of the FOLIO OWL file for cache invalidation."""  
        owl\_path \= self.folio.get\_owl\_path()  
        return hashlib.sha256(owl\_path.read\_bytes()).hexdigest()

    def \_build\_and\_cache(self):  
        """Embed all FOLIO labels and save to disk."""  
        concepts \= self.folio.get\_all\_classes()  
        self.labels \= \[c.label for c in concepts\]  
        self.iris \= \[c.iri for c in concepts\]  
        self.branches \= \[c.branch for c in concepts\]  
        self.definitions \= \[c.definition or "" for c in concepts\]

        \# Embed labels — include definition for richer vectors  
        texts\_to\_embed \= \[  
            f"{label}: {defn}" if defn else label  
            for label, defn in zip(self.labels, self.definitions)  
        \]  
        self.vectors \= self.provider.embed\_batch(texts\_to\_embed)

        \# Save cache  
        np.savez\_compressed(  
            self.cache\_path,  
            vectors=self.vectors,  
            labels=np.array(self.labels, dtype=object),  
            iris=np.array(self.iris, dtype=object),  
            branches=np.array(self.branches, dtype=object),  
        )

    def \_load\_cache(self):  
        """Load pre-computed embeddings from disk."""  
        data \= np.load(self.cache\_path, allow\_pickle=True)  
        self.vectors \= data\["vectors"\]  
        self.labels \= data\["labels"\].tolist()  
        self.iris \= data\["iris"\].tolist()  
        self.branches \= data\["branches"\].tolist()

    def \_build\_faiss\_index(self):  
        """Build FAISS index for fast nearest-neighbor search."""  
        dim \= self.vectors.shape\[1\]  
        self.index \= faiss.IndexFlatIP(dim)  \# inner product (cosine on normalized vectors)  
        self.index.add(self.vectors.astype(np.float32))

    def nearest\_neighbors(  
        self,  
        vector: np.ndarray,  
        k: int \= 5,  
        branch\_filter: str | None \= None,  
    ) \-\> list\[tuple\[str, str, float, str\]\]:  
        """  
        Find k nearest FOLIO concepts to the given vector.  
        Returns \[(iri, label, score, branch), ...\].  
          
        Optional branch\_filter restricts results to a single branch.  
        """  
        \# Search more than k if filtering by branch  
        search\_k \= k \* 10 if branch\_filter else k  
        scores, indices \= self.index.search(  
            vector.reshape(1, \-1).astype(np.float32), search\_k  
        )

        results \= \[\]  
        for score, idx in zip(scores\[0\], indices\[0\]):  
            if idx \< 0:  
                continue  
            if branch\_filter and self.branches\[idx\] \!= branch\_filter:  
                continue  
            results.append((  
                self.iris\[idx\],  
                self.labels\[idx\],  
                float(score),  
                self.branches\[idx\],  
            ))  
            if len(results) \>= k:  
                break

        return results

    def similarity(self, vector: np.ndarray, iri: str) \-\> float:  
        """Cosine similarity between a text vector and a specific FOLIO concept."""  
        try:  
            idx \= self.iris.index(iri)  
        except ValueError:  
            return 0.0  
        return float(np.dot(vector, self.vectors\[idx\]))

#### **6.2D.5 Cache Economics**

| Trigger | Action | Time | Cost (Local) | Cost (Cloud) |
| ----- | ----- | ----- | ----- | ----- |
| First startup | Embed all 18K FOLIO labels \+ build FAISS index | \~5–30 sec | $0.00 | \~$0.004–$0.023 |
| Subsequent startup (OWL unchanged) | Load cache from disk | \<1 sec | $0.00 | $0.00 |
| FOLIO OWL file updates | Re-embed all 18K labels \+ rebuild cache | \~5–30 sec | $0.00 | \~$0.004–$0.023 |
| User switches embedding model | Build new cache (old cache preserved) | \~5–30 sec | $0.00 | \~$0.004–$0.023 |
| User switches back to previous model | Load existing cache from disk | \<1 sec | $0.00 | $0.00 |

Annual re-embedding cost (assuming weekly FOLIO updates): **$0.00 (local)** or **under $2.00 (cloud)**.

Cache file size: \~28MB (18K × 768 dimensions × 4 bytes for `all-mpnet-base-v2`). Trivial.

---

### **6.3 Stage 3: Structure-Aware Chunking (Path B)**

*This stage runs in parallel with the EntityRuler (Path A). It is part of Path B (LLM pipeline).*

#### **6.3.1 Requirements**

1. Chunk the **entire document** — every section, clause, exhibit, schedule, signature block  
2. Respect section and paragraph boundaries (zero overlap)  
3. Keep each chunk under a configurable token limit (default: 3,000 tokens)  
4. If a single structural element exceeds the token limit, split at sentence boundaries using **NuPunkt-RS** for legal-domain sentence detection (preserves citations like "123 F.2d 456"), with LangChain `RecursiveCharacterTextSplitter(add_start_index=True)` as a secondary fallback  
5. Each chunk carries: `chunk_id`, `chunk_text`, `chunk_start_char`, `chunk_end_char`, `section_path`, `page`

#### **6.3.2 Implementation**

def build\_chunks(offset\_map, canonical\_text, max\_tokens=3000):  
    chunks \= \[\]  
    current\_elements \= \[\]  
    current\_tokens \= 0

    for elem in offset\_map:  
        elem\_text \= canonical\_text\[elem\["start\_char"\]:elem\["end\_char"\]\]  
        elem\_tokens \= estimate\_tokens(elem\_text)

        \# Single element exceeds limit: split at sentence boundaries  
        \# using NuPunkt-RS for legal-domain citation preservation  
        if elem\_tokens \> max\_tokens:  
            if current\_elements:  
                chunks.append(finalize\_chunk(current\_elements, canonical\_text))  
                current\_elements \= \[\]  
                current\_tokens \= 0

            sub\_chunks \= sentence\_split\_nupunkt(  
                elem\_text, elem\["start\_char"\], max\_tokens  
            )  
            chunks.extend(sub\_chunks)  
            continue

        \# Adding this element would exceed limit: flush  
        if current\_tokens \+ elem\_tokens \> max\_tokens and current\_elements:  
            chunks.append(finalize\_chunk(current\_elements, canonical\_text))  
            current\_elements \= \[\]  
            current\_tokens \= 0

        current\_elements.append(elem)  
        current\_tokens \+= elem\_tokens

    if current\_elements:  
        chunks.append(finalize\_chunk(current\_elements, canonical\_text))

    return chunks

def finalize\_chunk(elements, canonical\_text):  
    start \= elements\[0\]\["start\_char"\]  
    end \= elements\[-1\]\["end\_char"\]  
    return {  
        "chunk\_id": f"chunk\_{start}",  
        "chunk\_text": canonical\_text\[start:end\],  
        "chunk\_start\_char": start,  
        "chunk\_end\_char": end,  
        "section\_path": elements\[0\].get("section\_path"),  
        "page": elements\[0\].get("page")  
    }

#### **6.3.3 Zero-Overlap Rationale**

Legal text organizes into articles, sections, subsections, clauses. Docling extracts this structure. Overlap creates duplicate tag regions — the same phrase tagged twice in the overlapping zone of adjacent chunks. Zero overlap \+ structural boundaries eliminates this entirely.

#### **6.3.4 NuPunkt-RS Sentence Boundary Detection**

When the chunker falls back to sentence-level splitting, it uses NuPunkt-RS — a Rust-backed sentence boundary detector trained on legal corpora. NuPunkt-RS preserves citation integrity that standard sentence detectors destroy:

| Input Text | Standard Splitter | NuPunkt-RS |
| ----- | ----- | ----- |
| "See Smith v. Jones, 123 F.2d 456 (7th Cir. 2010). The court held..." | Splits at "v.", "F.", "2d.", "Cir." — 5 fragments | Keeps citation intact — 2 sentences |
| "The defendant, id. at 789, argued..." | Splits at "id." | Keeps "id." as abbreviation — 1 sentence |

NuPunkt-RS also serves as the sentence detector for the Judge's context window extraction (§6.7.3) and the dependency parser's sentence segmentation (§6.8A).

\# backend/app/services/sentence\_detector.py (NEW)

from nupunkt import sent\_tokenize

def detect\_sentences(text: str) \-\> list\[tuple\[int, int\]\]:  
    """  
    Split text into sentences using NuPunkt-RS (legal-domain trained).  
    Returns list of (start\_char, end\_char) tuples.  
      
    Performance: \~30M chars/sec (Rust backend).  
    A 500-page document (\~2.5M chars) completes in \~80ms.  
    """  
    sentences \= sent\_tokenize(text)  
    spans \= \[\]  
    offset \= 0  
    for sent in sentences:  
        start \= text.index(sent, offset)  
        spans.append((start, start \+ len(sent)))  
        offset \= start \+ len(sent)  
    return spans

def sentence\_split\_nupunkt(  
    text: str, global\_offset: int, max\_tokens: int  
) \-\> list\[dict\]:  
    """  
    Split an oversized text element at NuPunkt-RS sentence boundaries.  
    Groups sentences into sub-chunks that fit within max\_tokens.  
    Falls back to RecursiveCharacterTextSplitter if NuPunkt-RS  
    is unavailable.  
    """  
    try:  
        sentence\_spans \= detect\_sentences(text)  
    except Exception:  
        \# Fallback: use LangChain splitter if NuPunkt-RS unavailable  
        from langchain.text\_splitter import RecursiveCharacterTextSplitter  
        splitter \= RecursiveCharacterTextSplitter(  
            chunk\_size=max\_tokens \* 4,  \# rough char estimate  
            add\_start\_index=True,  
        )  
        docs \= splitter.create\_documents(\[text\])  
        return \[  
            {  
                "chunk\_id": f"chunk\_{global\_offset \+ doc.metadata\['start\_index'\]}",  
                "chunk\_text": doc.page\_content,  
                "chunk\_start\_char": global\_offset \+ doc.metadata\["start\_index"\],  
                "chunk\_end\_char": global\_offset \+ doc.metadata\["start\_index"\] \+ len(doc.page\_content),  
            }  
            for doc in docs  
        \]

    chunks \= \[\]  
    current\_start \= 0  
    current\_tokens \= 0  
    group\_start \= 0

    for sent\_start, sent\_end in sentence\_spans:  
        sent\_text \= text\[sent\_start:sent\_end\]  
        sent\_tokens \= estimate\_tokens(sent\_text)

        if current\_tokens \+ sent\_tokens \> max\_tokens and current\_tokens \> 0:  
            chunks.append({  
                "chunk\_id": f"chunk\_{global\_offset \+ group\_start}",  
                "chunk\_text": text\[group\_start:sent\_start\],  
                "chunk\_start\_char": global\_offset \+ group\_start,  
                "chunk\_end\_char": global\_offset \+ sent\_start,  
            })  
            group\_start \= sent\_start  
            current\_tokens \= 0

        current\_tokens \+= sent\_tokens

    \# Flush remaining  
    if group\_start \< len(text):  
        chunks.append({  
            "chunk\_id": f"chunk\_{global\_offset \+ group\_start}",  
            "chunk\_text": text\[group\_start:\],  
            "chunk\_start\_char": global\_offset \+ group\_start,  
            "chunk\_end\_char": global\_offset \+ len(text),  
        })

    return chunks

---

### **6.4 Stage 4: LLM Concept Identification**

#### **6.4.1 Core Design: Concept Text \+ Branch Only**

The LLM reads each chunk and returns a list of legal concept strings, each classified into a FOLIO branch. It does not return character offsets, FOLIO IRIs, or definitions.

**Why concept text instead of offsets:**

LLMs unreliably count characters. An LLM asked to return "start: 47, end: 60" for "force majeure" might return "start: 46, end: 59" (off-by-one), "start: 47, end: 55" (truncated boundary), or "start: 200, end: 213" (wrong location entirely). Every offset carries hallucination risk.

LLMs reliably identify and reproduce short strings from their input. An LLM asked to name the legal concept at a given location returns "force majeure" — a task aligned with core language-model capability.

Deterministic string matching (Aho-Corasick single-pass scan) locates the concept in the full canonical text with zero error. If the LLM slightly misquotes the concept (e.g., "breach of contracts" instead of "breach of contract"), the string match fails and the annotation gets discarded. The failure mode becomes *missed annotation*, never *wrong annotation*.

**Why no IRIs or definitions:**

Accurate IRI resolution requires the full ontology (\~500K tokens in context). `folio-python` resolves deterministically without any context window cost.

#### **6.4.2 LLM Prompt Specification**

The FOLIO branch list comes from FOLIO Mapper's branch metadata (`packages/core/src/folio/`), which defines 24 branches with display order and color coding. The LLM prompt uses the same branch names as FOLIO Mapper's UI. The LLM call itself runs through FOLIO Mapper's LLM provider abstraction (`backend/app/services/llm/`), supporting all 9 configured providers.

SYSTEM:  
You identify legal concepts in document text and classify each into  
one or more FOLIO ontology branches.

FOLIO BRANCHES:  
\- Area of Law  
\- Actors  
\- Legal Authorities  
\- Document Artifacts  
\- Objectives  
\- Services  
\- Events  
\- Industries  
\- Governmental Bodies  
\- Engagement Terms  
\- Currencies  
\- Data Formats  
\- Communication Modalities  
\- Asset Types  
\- Locations  
\- Narrative Descriptions  
\- Litigation Claims  
\- Contractual Clause

USER:  
CHUNK (chunk\_id: "{chunk\_id}"):  
"""  
{chunk\_text}  
"""

TASK: Identify legal concepts in this text. For each, return the  
exact text as it appears in the chunk and ALL plausible FOLIO branches.

OUTPUT FORMAT (JSON array, nothing else):  
\[  
  {"text": "Landlord", "branches": \["Actors"\]},  
  {"text": "Tenant", "branches": \["Actors"\]},  
  {"text": "force majeure", "branches": \["Contractual Clause", "Events"\]},  
  {"text": "United States", "branches": \["Locations", "Governmental Bodies"\]}  
\]

RULES:  
1\. Return the EXACT text as it appears in the chunk. Do not  
   paraphrase, pluralize, or alter capitalization.  
2\. Classify each concept into ALL plausible branches — err on the  
   side of over-inclusion. The downstream pipeline will filter  
   false positives deterministically; missed branches cannot be  
   recovered. When in doubt, include the branch.  
3\. Tag specific legal terms, not common English words.  
4\. If a concept appears multiple times in the chunk, list it  
   only ONCE — the system will find all occurrences.  
5\. Identify BOTH container and contained concepts when they  
   overlap. For example, "Breach of Contract" is a litigation  
   claim AND "Contract" within it is a document type. Return  
   BOTH as separate entries. Do not assume each word belongs  
   to only one concept — legal phrases frequently nest.

#### **6.4.3 LLM Output Example**

\[  
  {"text": "Landlord", "branches": \["Actors"\]},  
  {"text": "Tenant", "branches": \["Actors"\]},  
  {"text": "Premises", "branches": \["Asset Types", "Locations"\]},  
  {"text": "Term", "branches": \["Engagement Terms"\]},  
  {"text": "indemnification", "branches": \["Contractual Clause"\]},  
  {"text": "breach of contract", "branches": \["Litigation Claims", "Events"\]},  
  {"text": "contract", "branches": \["Document Artifacts"\]},  
  {"text": "State of New York", "branches": \["Locations", "Governmental Bodies"\]},  
  {"text": "governing law", "branches": \["Contractual Clause", "Area of Law"\]},  
  {"text": "law", "branches": \["Legal Authorities"\]}  
\]

Note: the LLM identifies both "breach of contract" (a litigation claim) and "contract" (a document type) as separate concepts, even though "contract" is a substring of "breach of contract." Similarly, "governing law" and "law" both appear. These overlapping entries are intentional — Rule 5 instructs the LLM to identify contained concepts alongside their containers. The downstream string matcher produces separate annotations at overlapping character ranges, and the frontend renders them as layered highlights.

Note: the LLM assigns "Premises" to both "Asset Types" and "Locations" because a leased premises functions as both a physical location and an asset. The downstream FOLIO resolution (Stage 5\) searches each branch independently — if FOLIO contains "Premises" as an asset type but not as a location, the resolution cache stores one hit and one miss. The miss gets discarded. No false positive reaches the user.

Note Rule 4: the LLM lists each concept once, even if "Landlord" appears six times in the chunk. The pipeline finds all occurrences deterministically.

**Why favor recall over precision in branch assignment:**

The LLM's branch classification serves as a **search scope** for FOLIO resolution, not a final label. Each branch the LLM suggests becomes one `(text, branch)` pair in the resolution cache. FOLIO Mapper's candidate search then validates whether a match exists in that branch. Three outcomes:

| FOLIO Match in Branch? | Result | Cost |
| ----- | ----- | ----- |
| **Match found** | Annotation created with correct branch | 1 resolution call (cached) |
| **No match** | Entry discarded silently | 1 wasted resolution call (cached) |
| **LLM omitted the correct branch** | Concept never searched in that branch → **permanent false negative** | Unrecoverable |

A wasted resolution call costs microseconds (it's a local `folio-python` search). A missed branch costs an annotation the user will never see. The asymmetry heavily favors over-inclusion.

#### **6.4.4 Hallucination Containment**

| LLM Error | Example | What Happens |
| ----- | ----- | ----- |
| Slight misquote | Returns "breach of contracts" but chunk contains "breach of contract" | Aho-Corasick finds no match → annotation discarded, logged |
| Fabricated concept | Returns "tortious interference" but chunk contains no such phrase | Aho-Corasick finds no match → discarded, logged |
| Wrong branch | Returns "Landlord" as "Contractual Clause" instead of "Actors" | Stage 5 resolution finds no match in that branch → discarded. If LLM also listed "Actors," that branch resolves correctly. |
| Extra branch (false positive) | Returns "Landlord" as both "Actors" and "Locations" | "Actors" resolves; "Locations" either fails FOLIO resolution (discarded at Stage 5\) or passes resolution but gets rejected by the Judge at Stage 6.5 using sentence context. |
| Missing branch (false negative) | Returns "United States" as "Locations" only, omitting "Governmental Bodies" | Annotation created for Locations only. Governmental Bodies annotation permanently missed. **This is the failure mode the over-inclusion strategy prevents.** |
| Duplicate listing | Returns "Landlord" twice | Deduplication in Stage 5 collapses to one entry per (text, branch) pair |
| Overlapping concepts | Returns both "breach of contract" and "contract" | Both resolve independently; string matcher produces overlapping annotations at correct character ranges — this is correct behavior, not an error |

Every failure produces either a correct annotation or a safely discarded one. No wrong annotation reaches the user. The one unrecoverable error — a missing branch — motivates the LLM prompt's instruction to err toward over-inclusion.

#### **6.4.4a LLM Response Parsing Failures**

The Stage 4 prompt requests a JSON array, but LLMs may return malformed output:

| Failure Mode | Detection | Recovery |
| ----- | ----- | ----- |
| **Malformed JSON** (truncated, extra text around JSON) | `json.loads()` raises `JSONDecodeError` | Extract JSON array via regex (`\[.*\]`); if that fails, retry once with same prompt. If retry fails, skip chunk and log. |
| **Prose instead of JSON** (LLM ignores format instruction) | Response contains no `[` character | Retry once with a stricter prompt suffix: "OUTPUT ONLY A JSON ARRAY. NO PROSE." If retry fails, skip chunk. |
| **Empty array** (`[]`) | Valid JSON, zero concepts | Accept as-is — the chunk may genuinely contain no legal concepts (e.g., a page of pure numbers or a table of contents). Log for review. |
| **Truncated response** (token limit hit mid-JSON) | JSON parsing fails; response ends without `]` | Append `]` and attempt parse. If that recovers valid entries, use them. Otherwise retry with a smaller chunk (split at NuPunkt-RS sentence boundary). |
| **Invalid structure** (objects missing `text` or `branches` fields) | Schema validation on each object | Skip malformed objects; keep valid ones. Log skipped objects. |

**Retry budget:** Each chunk gets at most 1 retry. After 2 consecutive chunk failures (original + retry), the pipeline logs a warning and continues — the EntityRuler path provides baseline coverage for skipped chunks. The pipeline never halts due to LLM parsing failures.

#### **6.4.5 Token Economics**

| Component | Tokens | Notes |
| ----- | ----- | ----- |
| Chunk text (input) | \~3,000 | Configurable |
| Branch list (input) | \~50 | Static, 18 branch names |
| Prompt template (input) | \~200 | Fixed |
| Annotations (output) | \~20 per unique concept | `{"text": "...", "branches": ["...", "..."]}` — slightly larger than single-branch due to array syntax |
| **Total per chunk** | **\~3,250 input \+ \~200 output** | Assuming \~10 unique concepts per chunk, \~1.5 branches per concept on average |

Compare to alternative approaches:

| Approach | Ontology Input Tokens Per Chunk |
| ----- | ----- |
| Full FOLIO ontology in context | \~500,000+ |
| Pruned branch subtree | \~5,000–20,000 |
| **Branch names only (this design)** | **\~50** |

---

### **6.4A Stage 4.5: Reconciliation — Merging Dual-Path Results**

#### **6.4A.1 Purpose**

The Reconciliation Layer receives outputs from both paths — EntityRuler matches (Path A) and LLM concept identifications (Path B) — and merges them into a single, deduplicated concept list. An LLM Judge resolves conflicts where the two systems disagree.

Neither path saw the other's output. The Reconciliation Layer is the first point where their results meet.

#### **6.4A.2 Reconciliation Categories**

For each EntityRuler match, the aligner checks whether the LLM identified the same concept text in any chunk covering that text range. Each match falls into one of five categories:

| Category | EntityRuler | LLM | Judge Needed? | Action |
| ----- | ----- | ----- | ----- | ----- |
| **A — Both agree** | Found "Landlord" | Found "Landlord" → Actors | No | Pass through. Use LLM's branch classification. Highest confidence. |
| **B — Both found, different branches** | Found "Term" (no branch) | Found "Term" → Engagement Terms | **Yes** | Judge reads context; determines correct branch(es). |
| **C — LLM only** | (no match) | Found "the agreement" → Document Artifacts | No | Pass through. Contextual discovery — EntityRuler can't catch these. |
| **D — EntityRuler only, LLM had opportunity** | Found "Interest" at pos 120 | Chunk covering pos 120 processed; LLM did NOT tag "Interest" | **Yes** | Judge reads context; determines whether EntityRuler match is a legal concept or common English. |
| **E — EntityRuler only, no LLM coverage** | Found "estoppel" at pos 8500 | No chunk covers pos 8500 (boundary edge case) | **Yes** | Judge reads context; determines branch classification. |

#### **6.4A.3 Why the Judge Decides Conflicts (Not Hardcoded Rules)**

Category D is the critical case. The EntityRuler matched "Interest" because "Interest" is a FOLIO label. The LLM read the surrounding text — "counsel expressed no interest in pursuing the claim" — and correctly chose not to tag it. A hardcoded rule ("trust the LLM's omission") would work here. But consider:

* "The Borrower shall pay Interest at a rate of 5% per annum" — the LLM missed a legitimate legal concept. The EntityRuler caught it. The hardcoded rule would incorrectly discard it.

Only an LLM Judge reading the surrounding context can distinguish these cases reliably. The Judge knows the conflict source (EntityRuler matched, LLM chose not to tag) and uses that framing to focus its analysis.

#### **6.4A.4 Reconciliation Judge Prompt**

SYSTEM:  
You reconcile conflicts between two independent concept identification  
systems applied to legal documents.

System A (EntityRuler): A deterministic matcher that finds exact matches  
  against 18,000 FOLIO ontology labels. High recall, no context awareness.  
  It matches every occurrence of a FOLIO label regardless of meaning.

System B (LLM): A language model that reads text in context and identifies  
  legal concepts. Context-aware but may miss concepts.

Your task: Given a conflict between these systems, read the surrounding  
text and determine whether the concept functions as a legal term in  
this specific context.

OUTPUT FORMAT (JSON array, one object per occurrence):  
\[  
  {"occurrence\_start": 120, "keep": true, "branches": \["Engagement Terms"\],  
   "reason": "Financial interest on a loan — matches FOLIO concept"},  
  {"occurrence\_start": 5500, "keep": false, "branches": \[\],  
   "reason": "Common English 'interest' meaning curiosity — not a legal concept"}  
\]

USER:  
CONFLICT TYPE: {category\_B | category\_D | category\_E}  
CONCEPT: "{concept\_text}"  
FOLIO LABEL: "{folio\_label}" (IRI: {folio\_iri})  
FOLIO DEFINITION: "{folio\_definition}"

OCCURRENCES:  
1\. Position {start}: "...{500 chars of surrounding context}..."  
2\. Position {start}: "...{500 chars of surrounding context}..."

{For Category B:}  
LLM CLASSIFICATION: {branches}  
EntityRuler had no branch classification.

{For Category D:}  
The LLM processed the chunk containing this text and chose NOT to  
tag this concept. The EntityRuler matched it as a FOLIO label.

{For Category E:}  
No LLM chunk covered this text range. The EntityRuler matched it  
as a FOLIO label.

TASK: For each occurrence, determine whether the concept functions  
as the FOLIO legal concept in this specific context. If yes, assign  
to FOLIO branch(es). If no, reject.

#### **6.4A.5 Embedding-Assisted Triage**

Before routing Category B, D, and E conflicts to the LLM Judge, the Reconciliation Layer applies embedding-based triage to auto-resolve obvious cases. For each conflict, the pipeline embeds the surrounding sentence and computes cosine similarity against the FOLIO concept's definition embedding (pre-computed in the FOLIO embedding index):

| Embedding Similarity to FOLIO Definition | Action | Judge Call? |
| ----- | ----- | ----- |
| \> 0.85 | Auto-confirm: the concept clearly matches the FOLIO definition in context | No — save LLM tokens |
| 0.50 – 0.85 | Ambiguous: send to LLM Judge for contextual reasoning | Yes |
| \< 0.50 | Auto-reject: the concept clearly does NOT match the FOLIO definition in context | No — save LLM tokens |

**Example — "Interest" at two positions:**

* Position 120: "The Borrower shall pay Interest at a rate of 5%..." → sentence embedding vs. FOLIO "Interest" definition (financial charge) → cosine similarity **0.91**. Auto-confirm. No Judge call.  
* Position 5500: "Counsel expressed no interest in pursuing..." → same comparison → cosine similarity **0.28**. Auto-reject. No Judge call.  
* Position 8200: "The party's interest in the property..." → cosine similarity **0.67**. Ambiguous (financial interest? ownership interest?). Send to Judge.

**Token savings:** Embedding triage auto-resolves \~40–60% of conflicts that would otherwise consume LLM Judge tokens. The 35–65 conflict cases per 100-page document drop to \~15–30 Judge calls.

**Threshold calibration:** The thresholds (0.85 confirm, 0.50 reject) are conservative defaults. Start conservative (0.90 / 0.40) to minimize errors, then tune based on Judge agreement rates. If the Judge consistently agrees with the embedding triage on auto-confirmed cases, lower the confirm threshold. If the Judge frequently overrides auto-rejections, raise the reject threshold.

#### **6.4A.6 Batching and Token Economics**

The Reconciliation Judge batches all occurrences of one concept in a single call (same batching pattern as the Branch Judge in §6.7.5). Embedding triage reduces the volume sent to the Judge. For a 100-page contract:

| Category | Estimated Count | Auto-Resolved by Embedding | Judge Calls | Tokens per Call | Total Tokens |
| ----- | ----- | ----- | ----- | ----- | ----- |
| A (both agree) | \~60 concepts | — | 0 | — | 0 |
| B (different branches) | \~5–10 concepts | \~2–4 | 3–6 | \~2,000 | \~6K–12K |
| C (LLM only) | \~10–15 concepts | — | 0 | — | 0 |
| D (EntityRuler only, LLM had chance) | \~30–50 matches | \~15–25 | 10–20 | \~2,000 | \~20K–40K |
| E (boundary edge case) | \~0–5 matches | \~0–2 | 0–3 | \~2,000 | \~0–6K |
| **Total** |  | **\~17–31 auto-resolved** | **\~13–29 calls** |  | **\~26K–58K tokens** |

Compared to pre-triage estimates (\~40K–80K tokens), embedding triage saves \~30–40% of Reconciliation Judge token cost.

#### **6.4A.6 Implementation**

\# backend/app/services/reconciliation\_service.py (NEW)

from enum import Enum

class ReconciliationCategory(Enum):  
    A\_BOTH\_AGREE \= "both\_agree"  
    B\_DIFFERENT\_BRANCHES \= "different\_branches"  
    C\_LLM\_ONLY \= "llm\_only"  
    D\_ENTITY\_RULER\_LLM\_SKIPPED \= "entity\_ruler\_only\_llm\_skipped"  
    E\_ENTITY\_RULER\_NO\_LLM\_COVERAGE \= "entity\_ruler\_only\_no\_coverage"

def categorize\_matches(  
    entity\_ruler\_matches: list\[dict\],  
    llm\_concepts\_by\_chunk: dict\[str, list\[dict\]\],  
    chunk\_ranges: list\[tuple\[int, int\]\],  
) \-\> dict\[ReconciliationCategory, list\[dict\]\]:  
    """  
    Align EntityRuler matches with LLM results.  
    Classify each match into reconciliation categories A–E.  
    """  
    categorized \= {cat: \[\] for cat in ReconciliationCategory}

    \# Build a lookup: for each concept text (lowered), which chunks  
    \# did the LLM tag it in?  
    llm\_concepts\_set \= {}  
    for chunk\_id, concepts in llm\_concepts\_by\_chunk.items():  
        for concept in concepts:  
            key \= concept\["text"\].lower()  
            if key not in llm\_concepts\_set:  
                llm\_concepts\_set\[key\] \= {  
                    "branches": concept\["branches"\],  
                    "chunk\_ids": set(),  
                }  
            llm\_concepts\_set\[key\]\["chunk\_ids"\].add(chunk\_id)  
            \# Merge branches from multiple chunks  
            for b in concept\["branches"\]:  
                if b not in llm\_concepts\_set\[key\]\["branches"\]:  
                    llm\_concepts\_set\[key\]\["branches"\].append(b)

    for match in entity\_ruler\_matches:  
        text\_lower \= match\["text"\].lower()  
        llm\_entry \= llm\_concepts\_set.get(text\_lower)

        if llm\_entry:  
            \# Both found — check branch agreement  
            if match.get("branch") and match\["branch"\] in llm\_entry\["branches"\]:  
                categorized\[ReconciliationCategory.A\_BOTH\_AGREE\].append({  
                    \*\*match,  
                    "llm\_branches": llm\_entry\["branches"\],  
                })  
            else:  
                categorized\[ReconciliationCategory.B\_DIFFERENT\_BRANCHES\].append({  
                    \*\*match,  
                    "llm\_branches": llm\_entry\["branches"\],  
                })  
        else:  
            \# EntityRuler only — did the LLM have a chance?  
            match\_in\_any\_chunk \= any(  
                cs \<= match\["start"\] and match\["end"\] \<= ce  
                for cs, ce in chunk\_ranges  
            )  
            if match\_in\_any\_chunk:  
                categorized\[ReconciliationCategory.D\_ENTITY\_RULER\_LLM\_SKIPPED\].append(match)  
            else:  
                categorized\[ReconciliationCategory.E\_ENTITY\_RULER\_NO\_LLM\_COVERAGE\].append(match)

    \# Category C: LLM concepts not found by EntityRuler  
    er\_texts \= {m\["text"\].lower() for m in entity\_ruler\_matches}  
    for text\_lower, entry in llm\_concepts\_set.items():  
        if text\_lower not in er\_texts:  
            categorized\[ReconciliationCategory.C\_LLM\_ONLY\].append({  
                "text": text\_lower,  
                "branches": entry\["branches"\],  
                "source": "llm",  
            })

    return categorized

async def reconcile(  
    categorized: dict,  
    canonical\_text: str,  
    judge\_service,  
) \-\> list\[dict\]:  
    """  
    Merge categorized matches into a unified concept list.  
    Categories A and C pass through directly.  
    Categories B, D, E go through the Reconciliation Judge.  
      
    Returns a merged list of (text, branches, source) entries  
    ready for Stage 5 resolution.  
    """  
    merged \= \[\]

    \# Category A: pass through with LLM branches  
    for match in categorized\[ReconciliationCategory.A\_BOTH\_AGREE\]:  
        merged.append({  
            "text": match\["text"\],  
            "branches": match\["llm\_branches"\],  
            "source": "both",  
            "confidence": "high",  
        })

    \# Category C: pass through LLM-only discoveries  
    for match in categorized\[ReconciliationCategory.C\_LLM\_ONLY\]:  
        merged.append({  
            "text": match\["text"\],  
            "branches": match\["branches"\],  
            "source": "llm",  
            "confidence": "medium",  
        })

    \# Categories B, D, E: send to Reconciliation Judge  
    conflicts \= (  
        categorized\[ReconciliationCategory.B\_DIFFERENT\_BRANCHES\]  
        \+ categorized\[ReconciliationCategory.D\_ENTITY\_RULER\_LLM\_SKIPPED\]  
        \+ categorized\[ReconciliationCategory.E\_ENTITY\_RULER\_NO\_LLM\_COVERAGE\]  
    )

    if conflicts:  
        judge\_results \= await judge\_service.reconcile\_conflicts(  
            conflicts, canonical\_text  
        )  
        for result in judge\_results:  
            if result\["keep"\]:  
                merged.append({  
                    "text": result\["text"\],  
                    "branches": result\["branches"\],  
                    "source": "reconciliation\_judge",  
                    "confidence": "judge\_confirmed",  
                })

    return merged

#### **6.4A.7 Progressive Reconciliation**

Reconciliation runs per-chunk as LLM results stream in. When chunk N's LLM results arrive:

1. The aligner categorizes EntityRuler matches within chunk N's text range against chunk N's LLM concepts.  
2. Category A matches upgrade from "preliminary" to "confirmed" on the frontend (solid highlight).  
3. Category D conflicts (EntityRuler found, LLM skipped) go to the Reconciliation Judge.  
4. Judge results stream back — confirmed concepts upgrade to "confirmed." Rejected concepts transition to "rejected" state — dimmed but still visible, with the Judge's reason accessible on hover and a "Resurrect" affordance (see §6.8.5).

#### **6.4A.8 Three Annotation States**

Every annotation passes through a lifecycle of three visual states:

| State | Visual Treatment | How It Gets Here | User Actions |
| ----- | ----- | ----- | ----- |
| **Preliminary** | Lighter highlight \+ uncertainty indicator (dotted border, "?" badge). High-confidence: solid highlight awaiting confirmation. Low-confidence: reduced opacity \+ dotted border. | EntityRuler match, before LLM reconciliation completes | Click to see partial metadata; tooltip: "Awaiting confirmation" |
| **Confirmed** | Full highlight, branch-colored, solid border | Both paths agreed (Category A); or Judge confirmed (Categories B/D/E); or user resurrected | Click for full FOLIO metadata: label, definition, IRI, ontology path, ancestry tree |
| **Rejected** | Very faint highlight or strikethrough; collapsed by default but visible; small "×" indicator | Reconciliation Judge rejected; or Branch Judge rejected | Hover: see Judge's rejection reason. Click "Resurrect" to override (see §6.8.5). |

Rejected annotations remain visible in the document. They do not disappear. The user can always resurrect them. This transparency builds trust — the user sees the pipeline's full reasoning, not a filtered result.

**State transitions:**

EntityRuler match → \[PRELIMINARY\]  
                        │  
           ┌────────────┼────────────┐  
           │            │            │  
    Category A    Category D/E    Category C  
    (both agree)  (conflict)     (LLM only)  
           │            │            │  
           ▼            ▼            ▼  
      \[CONFIRMED\]  Judge decides  \[CONFIRMED\]  
                    │       │  
                    ▼       ▼  
             \[CONFIRMED\] \[REJECTED\]  
                              │  
                         User clicks  
                         "Resurrect"  
                              │  
                              ▼  
                    \[CONFIRMED \+ user\_override\]

---

### **6.5 Stage 5: Concept Deduplication \+ FOLIO Resolution (Resolve Once, Use Many)**

This stage collects every unique concept from the Reconciliation Layer's merged output, resolves each against `folio-python` exactly once, and builds a **concept resolution cache** that all downstream stages reference.

#### **6.5.1 Why Resolve Once**

A 90-page commercial lease might produce these LLM results across 47 chunks:

| Concept | Chunks Where LLM Identified It | Total Occurrences in Document |
| ----- | ----- | ----- |
| "Landlord" | 38 of 47 chunks | \~200 |
| "Tenant" | 35 of 47 chunks | \~180 |
| "Premises" | 22 of 47 chunks | \~90 |
| "force majeure" | 2 of 47 chunks | \~4 |
| "indemnification" | 5 of 47 chunks | \~12 |

Without caching, the pipeline would call `folio-python` \~500+ times (once per chunk-mention). With resolve-once caching, it calls `folio-python` \~60 times (once per unique concept-text \+ branch pair, with \~1.5 branches per concept average). For a 500-page filing with \~200 unique concepts and \~300 concept-branch pairs, the reduction grows to **500x or more** (tens of thousands of chunk-mentions vs. \~300 resolution calls).

#### **6.5.2 Building the Resolution Cache**

from folio import FOLIO

folio \= FOLIO()

def build\_resolution\_cache(all\_chunk\_results: list\[list\[dict\]\]) \-\> dict:  
    """  
    Collect all LLM-identified concepts across all chunks.  
    Flatten multi-branch assignments into individual (text, branch) pairs.  
    Deduplicate by (text\_lower, branch).  
    Resolve each unique pair via FOLIO Mapper's candidate search.  
    Return a cache: (text\_lower, branch) → resolution\_result.  
      
    The LLM returns {"text": "United States", "branches": \["Locations",  
    "Governmental Bodies"\]}. This function creates TWO cache entries:  
      ("united states", "Locations") → resolution\_result  
      ("united states", "Governmental Bodies") → resolution\_result  
      
    Each resolves independently. Branches with no FOLIO match get  
    discarded — the false positive is caught here, not by the LLM.  
      
    FOLIO Mapper cross-reference:  
      \- Candidate search: backend/app/routers/mapping\_router.py  
        → POST /api/mapping/candidates  
      \- FOLIO singleton \+ search: backend/app/services/folio\_service.py  
      \- Score cutoff calculation: packages/core/src/mapping/  
    """  
    \# Step 1: Flatten multi-branch into (concept, branch) pairs  
    unique\_concepts \= {}  
    for chunk\_result in all\_chunk\_results:  
        for ann in chunk\_result:  
            text\_lower \= ann\["text"\].lower().strip()  
            \# LLM returns "branches" (array), not "branch" (string)  
            branches \= ann.get("branches", \[ann.get("branch", "")\])  
            for branch in branches:  
                key \= (text\_lower, branch)  
                if key not in unique\_concepts:  
                    unique\_concepts\[key\] \= ann\["text"\]  \# preserve original case

    \# Step 2: Resolve each unique (concept, branch) pair once  
    cache \= {}  
    for (text\_lower, branch), original\_text in unique\_concepts.items():  
        resolution \= resolve\_concept(original\_text, branch)  
        cache\[(text\_lower, branch)\] \= resolution

    return cache

def resolve\_concept(concept\_text: str, branch: str) \-\> dict:  
    """  
    Resolve a single concept via FOLIO Mapper's candidate search.  
      
    FOLIO Mapper cross-reference:  
      \- This calls POST /api/mapping/candidates  
        (backend/app/routers/mapping\_router.py)  
      \- Which invokes folio\_service.search()  
        (backend/app/services/folio\_service.py)  
      \- Fuzzy matching uses rapidfuzz  
        (already a FOLIO Mapper dependency)  
      \- Branch filtering uses FOLIO Mapper's branch metadata  
        (packages/core/src/folio/)  
    """  
    \# Call FOLIO Mapper's candidate search  
    \# (In production, this calls the /api/mapping/candidates endpoint  
    \#  or invokes folio\_service directly if running in-process)  
    results \= folio.search(concept\_text)

    \# Filter to target branch  
    branch\_matches \= \[r for r in results if is\_in\_branch(r, branch)\]

    \# If no branch match, check other branches  
    \# (LLM may have classified incorrectly)  
    if not branch\_matches and results:  
        best \= results\[0\]  
        actual\_branch \= get\_branch(best)  
        return {  
            "resolved": True,  
            "match\_type": "branch\_corrected",  
            "original\_branch": branch,  
            "actual\_branch": actual\_branch,  
            "iri": best.iri,  
            "label": best.label,  
            "definition": getattr(best, "definition", ""),  
        }

    \# Try fuzzy matching  
    if not branch\_matches:  
        fuzzy \= fuzzy\_search(concept\_text, branch)  
        if fuzzy:  
            best \= fuzzy\[0\]  
            return {  
                "resolved": True,  
                "match\_type": "fuzzy",  
                "iri": best.iri,  
                "label": best.label,  
                "definition": getattr(best, "definition", ""),  
            }

    \# No match at all  
    if not branch\_matches:  
        return {  
            "resolved": False,  
            "span\_text": concept\_text,  
            "branch": branch,  
            "flag": "no\_folio\_match"  
        }

    \# Best match in correct branch  
    best \= branch\_matches\[0\]  
    return {  
        "resolved": True,  
        "match\_type": "exact",  
        "iri": best.iri,  
        "label": best.label,  
        "definition": getattr(best, "definition", ""),  
    }

#### **6.5.3 Resolution Outcomes**

| Outcome | Est. Frequency | Action |
| ----- | ----- | ----- |
| **Exact match in correct branch** | \~70% | Cache and apply to all occurrences |
| **Match in wrong branch** (LLM misclassified) | \~15% | Cache with corrected branch; log for prompt tuning |
| **Fuzzy match (rapidfuzz)** | \~8% | Cache with `match_type: fuzzy`; flag for optional review |
| **Fuzzy match (embedding fallback)** | \~4% | When rapidfuzz confidence \< 0.70, fall back to embedding similarity against the FOLIO label index. Cache with `match_type: embedding_fuzzy` if similarity \> 0.85. |
| **No match** | \~3% | Cache as unresolved; flag for human review; do not stamp onto occurrences |

#### **6.5.4 Embedding-Augmented Resolution Fallback**

When `rapidfuzz` returns a low-confidence match (below 0.70 string similarity), the pipeline falls back to the shared EmbeddingService. The concept text is embedded and compared against the pre-computed FOLIO label embedding index, scoped to the candidate branch:

\# In resolution\_cache.py — augment existing resolution logic:

async def resolve\_with\_embedding\_fallback(  
    concept\_text: str,  
    branch: str,  
    folio\_service,  
    embedding\_service: "EmbeddingService",  
) \-\> dict:  
    """  
    Resolve a concept against FOLIO. If rapidfuzz confidence is low,  
    fall back to embedding similarity for semantic matching.  
      
    "Property representative" → rapidfuzz 0.42 vs "Real Estate Broker"  
    → embedding similarity 0.87 → match found.  
    """  
    \# Primary: rapidfuzz via FOLIO Mapper's existing search  
    result \= folio\_service.search(concept\_text, branch=branch)

    if result and result.confidence \>= 0.70:  
        return result  \# High-confidence string match — use it

    \# Fallback: embedding similarity  
    concept\_vector \= embedding\_service.embed(concept\_text)  
    neighbors \= embedding\_service.nearest\_neighbors(  
        vector=concept\_vector,  
        k=5,  
        branch\_filter=branch,  
    )

    for iri, label, score, branch\_name in neighbors:  
        if score \>= 0.85:  
            \# Semantic match found  
            folio\_class \= folio\_service.get\_class(iri)  
            return {  
                "resolved": True,  
                "iri": iri,  
                "label": label,  
                "definition": folio\_class.definition,  
                "match\_type": "embedding\_fuzzy",  
                "confidence": score,  
                "branch": branch\_name,  
            }

    \# No match at either level  
    return {"resolved": False, "match\_type": "none"}

This fallback costs almost nothing — 1 embedding call (\~0.25ms local) \+ 1 FAISS nearest-neighbor search (\~0.01ms) per low-confidence concept. For a 100-page contract, maybe 5–10 concepts hit this path. Total added time: \<50ms.

---

### **6.6 Stage 6: Global String Matching (Locate Every Occurrence)**

With the resolution cache built, the pipeline scans the **full canonical text** (not individual chunks) to find every occurrence of every resolved concept. This ensures consistent annotation even if the LLM missed a concept in some chunks.

#### **6.6.1 Why Scan the Full Document**

The LLM might identify "force majeure" in chunk 32 but miss it in chunk 44\. Scanning the full canonical text for every resolved concept catches all occurrences regardless of which chunks the LLM flagged them in.

This also means the LLM's chunk-level results serve as a **concept discovery** mechanism, not a **per-occurrence tagger**. The LLM finds the vocabulary; deterministic matching finds the locations.

#### **6.6.2 Why Not Regex**

The naive approach — run a separate regex scan per concept — scales poorly for long legal documents:

| Document | Unique Concept-Branch Pairs | Canonical Text | Regex: Full Passes | Regex: Character Comparisons |
| ----- | ----- | ----- | ----- | ----- |
| 30-page lease | \~60 | \~150K chars | 60 | 9 million |
| 100-page M\&A agreement | \~200 | \~500K chars | 200 | 100 million |
| 500-page regulatory filing | \~300 | \~2.5M chars | 300 | 750 million |
| Batch: 500 × 100-page contracts | \~200 avg | \~500K each | 100,000 total | 50 billion |

Each regex scan walks the entire canonical text independently, learning nothing from previous scans. For a 500-page document with 300 patterns, the regex approach runs 300 full passes over 2.5 million characters.

#### **6.6.3 Matching Strategy: Aho-Corasick \+ Character-Class Boundaries**

The pipeline uses a two-phase approach: **Aho-Corasick** for single-pass multi-pattern matching, then **character-class boundary validation** to reject substring collisions. This combination scans the text once regardless of pattern count.

**Phase 1 — Aho-Corasick automaton:**

Build a finite-state automaton from all resolved concept strings. Scan the canonical text once. The automaton fires at every match position for every concept simultaneously — "Breach of Contract" at position 100 and "Contract" at position 111 both emerge from the same single pass.

**Phase 2 — Character-class boundary validation:**

For each Aho-Corasick match, check whether the match starts and ends at a word boundary. A "word character" includes alphanumeric characters and hyphens — so "Co-Landlord" is one word, and "Landlord" at position 3 does NOT start at a word boundary. This rejects substring collisions and hyphenated-compound false positives without regex.

**Performance comparison:**

| Document | Patterns | Regex: Passes × Time | Aho-Corasick: Passes × Time |
| ----- | ----- | ----- | ----- |
| 30 pages (150K chars) | 60 | 60 passes, \~60ms | 1 pass, \~5ms |
| 100 pages (500K chars) | 200 | 200 passes, \~400ms | 1 pass, \~12ms |
| 500 pages (2.5M chars) | 300 | 300 passes, \~1.5s | 1 pass, \~30ms |
| Batch: 500 × 100 pages | 200 avg | 100K passes, \~200s | 500 passes, \~6s |

Pattern count does not affect Aho-Corasick scan time — only text length and match count matter.

#### **6.6.4 Implementation**

import ahocorasick  
from bisect import bisect\_right

def compute\_word\_boundaries(text: str) \-\> tuple\[set, set\]:  
    """  
    Single O(n) pass over the canonical text.  
    Mark every position where a word starts and ends.  
      
    A "word character" is alphanumeric or hyphen.  
    This means "Co-Landlord" is ONE word (hyphen joins it),  
    while "Breach of Contract" is THREE words (spaces separate).  
      
    For a 500-page document (\~2.5M chars), this runs in \<25ms.  
    No external library required.  
    """  
    starts \= set()  
    ends \= set()  
    in\_word \= False

    for i, ch in enumerate(text):  
        is\_word\_char \= ch.isalnum() or ch \== '-'  
        if is\_word\_char and not in\_word:  
            starts.add(i)  
            in\_word \= True  
        elif not is\_word\_char and in\_word:  
            ends.add(i)  
            in\_word \= False

    if in\_word:  
        ends.add(len(text))

    return starts, ends

def build\_automaton(resolution\_cache: dict) \-\> ahocorasick.Automaton:  
    """  
    Build an Aho-Corasick automaton from all resolved concept strings.  
      
    Each resolved (text\_lower, branch) pair becomes an automaton entry.  
    The automaton returns all matching (text, branch) pairs at each  
    position in a single pass.  
      
    For 300 patterns averaging 15 chars each, construction takes \<1ms.  
    """  
    A \= ahocorasick.Automaton()

    for (text\_lower, branch), resolution in resolution\_cache.items():  
        if not resolution\["resolved"\]:  
            continue  
        \# Store the key so we can look up the full resolution later  
        \# ahocorasick allows multiple values per string via a list  
        existing \= A.get(text\_lower, \[\])  
        existing.append((text\_lower, branch))  
        A.add\_word(text\_lower, existing)

    A.make\_automaton()  
    return A

def locate\_all\_occurrences(canonical\_text: str, resolution\_cache: dict,  
                           offset\_map: list) \-\> list:  
    """  
    Single-pass multi-pattern matching using Aho-Corasick.  
      
    1\. Pre-compute word boundaries (O(n), one pass)  
    2\. Build Aho-Corasick automaton from all resolved concepts  
    3\. Scan canonical text ONCE — automaton fires at every match  
    4\. Validate each match against word boundaries (O(1) per match)  
    5\. Attach resolution metadata and provenance  
      
    For a 500-page document (2.5M chars, 300 patterns, \~10K matches):  
      \- Boundary computation: \~25ms  
      \- Automaton construction: \~1ms  
      \- Single-pass scan \+ validation: \~30ms  
      \- Total: \~56ms (vs \~1.5s for 300 regex passes)  
      
    Overlapping spans emerge naturally: "Breach of Contract" fires  
    at position 100, "Contract" fires at position 111 — both from  
    the same single scan. No special overlap logic needed.  
      
    Multi-branch handling: "United States" resolved in both  
    "Locations" and "Governmental Bodies" produces TWO automaton  
    entries for the same string. Each fires at every occurrence,  
    creating two annotations per position.  
    """  
    text\_lower \= canonical\_text.lower()

    \# Phase 1: Pre-compute word boundaries  
    word\_starts, word\_ends \= compute\_word\_boundaries(text\_lower)

    \# Phase 2: Build automaton  
    automaton \= build\_automaton(resolution\_cache)

    \# Phase 3: Single-pass scan  
    annotations \= \[\]

    for end\_idx, entries in automaton.iter(text\_lower):  
        for (concept\_lower, branch) in entries:  
            start\_idx \= end\_idx \- len(concept\_lower) \+ 1  
            match\_end \= end\_idx \+ 1

            \# Phase 4: Word-boundary validation (O(1) per match)  
            \# Match must start at a word boundary AND end at one.  
            \# Rejects: "Contract" inside "Subcontractor" (start not at boundary)  
            \# Rejects: "Landlord" inside "Co-Landlord" (start not at boundary  
            \#          because hyphen is a word character)  
            \# Allows:  "Contract" inside "Breach of Contract" (space \= boundary)  
            if start\_idx not in word\_starts:  
                continue  
            if match\_end not in word\_ends:  
                continue

            \# Phase 5: Build annotation  
            resolution \= resolution\_cache\[(concept\_lower, branch)\]  
            actual\_text \= canonical\_text\[start\_idx:match\_end\]  
            provenance \= find\_provenance(start\_idx, offset\_map)

            annotations.append({  
                "start": start\_idx,  
                "end": match\_end,  
                "text": actual\_text,  
                "iri": resolution\["iri"\],  
                "label": resolution\["label"\],  
                "definition": resolution\["definition"\],  
                "branch": resolution.get("actual\_branch", branch),  
                "match\_type": resolution\["match\_type"\],  
                "provenance": provenance,  
            })

    \# Sort: position first, longest span first, then branch name  
    annotations.sort(  
        key=lambda a: (a\["start"\], \-(a\["end"\] \- a\["start"\]), a\["branch"\])  
    )

    return annotations

def find\_provenance(global\_start: int, offset\_map: list) \-\> dict:  
    """  
    Binary search the offset map to find which structural element  
    contains this character position. Return page, section path, etc.  
      
    Uses bisect for O(log n) lookup instead of linear scan —  
    important for 500-page documents with 5,000+ offset map entries.  
    """  
    \# offset\_map is sorted by start\_char  
    starts \= \[e\["start\_char"\] for e in offset\_map\]  
    idx \= bisect\_right(starts, global\_start) \- 1  
    if idx \>= 0 and offset\_map\[idx\]\["start\_char"\] \<= global\_start \< offset\_map\[idx\]\["end\_char"\]:  
        elem \= offset\_map\[idx\]  
        return {  
            "page": elem\["page"\],  
            "section\_path": elem.get("section\_path"),  
            "element\_type": elem.get("element\_type"),  
        }  
    return {"page": None, "section\_path": None}

#### **6.6.5 Regex Fallback**

For environments where `pyahocorasick` cannot be installed (e.g., restricted deployment environments), the pipeline falls back to per-concept regex scanning with the same word-boundary logic:

import re

def locate\_all\_occurrences\_regex(canonical\_text: str, resolution\_cache: dict,  
                                 offset\_map: list) \-\> list:  
    """  
    Fallback: per-concept regex scanning.  
    Same output as the Aho-Corasick implementation, but runs  
    one full text pass per resolved concept-branch pair.  
      
    Use only when pyahocorasick is unavailable.  
    """  
    annotations \= \[\]

    for (text\_lower, branch), resolution in resolution\_cache.items():  
        if not resolution\["resolved"\]:  
            continue

        escaped \= re.escape(text\_lower)  
        pattern \= re.compile(  
            r'(?\<\!\[a-zA-Z0-9\\-\])' \+ escaped \+ r'(?\!\[a-zA-Z0-9\\-\])',  
            re.IGNORECASE  
        )

        for match in pattern.finditer(canonical\_text):  
            actual\_text \= canonical\_text\[match.start():match.end()\]  
            provenance \= find\_provenance(match.start(), offset\_map)

            annotations.append({  
                "start": match.start(),  
                "end": match.end(),  
                "text": actual\_text,  
                "iri": resolution\["iri"\],  
                "label": resolution\["label"\],  
                "definition": resolution\["definition"\],  
                "branch": resolution.get("actual\_branch", branch),  
                "match\_type": resolution\["match\_type"\],  
                "provenance": provenance,  
            })

    annotations.sort(  
        key=lambda a: (a\["start"\], \-(a\["end"\] \- a\["start"\]), a\["branch"\])  
    )  
    return annotations

#### **6.6.6 Overlapping Spans, Nested Concepts, and Substring Collisions**

The Aho-Corasick automaton searches for all resolved concepts simultaneously in a single pass. Because each concept fires independently, the output naturally contains annotations at overlapping character ranges. The character-class boundary validation then distinguishes valid nested concepts from substring collisions. Four scenarios:

**Scenario 1 — Nested concepts (desired overlap):**

Text:  "...alleging Breach of Contract under the terms..."  
                   ^^^^^^^^^^^^^^^^^^^  
                   |         ^^^^^^^^  
                   |         Contract (Document Artifacts, pos 111–119)  
                   Breach of Contract (Litigation Claims, pos 100–119)

The automaton fires twice during a single scan: once for "breach of contract" ending at position 119, once for "contract" ending at position 119\. Boundary validation confirms both: "Contract" starts at position 111 (in `word_starts` — space precedes it) and ends at position 119 (in `word_ends` — space follows). Both annotations emit. **Correct and desired.**

**Scenario 2 — Substring collision (undesired match):**

Text:  "...hired the Subcontractor to perform..."  
                     ^^^^^^^^^^^^^  
                     Subcontractor (pos 200–213)  
                          ^^^^^^^^  
                          ✗ "Contract" should NOT match here

The automaton fires for "contract" ending at position 213 (inside "Subcontractor"). Boundary validation rejects: the start position of "contract" is NOT in `word_starts` because the preceding character "b" is alphanumeric — no word boundary. **Correctly rejected.**

**Scenario 3 — Compound concepts (both valid, overlapping):**

Text:  "...the Contract Law provisions require..."  
             ^^^^^^^^^^^^  
             |        ^^^  
             |        Law (Legal Authorities, pos 309–312)  
             Contract Law (Area of Law, pos 300–312)  
             ^^^^^^^^  
             Contract (Document Artifacts, pos 300–308)

The automaton fires three times in one pass. Boundary validation confirms all three — each starts and ends at word boundaries. Three annotations emit. **Correct and desired.**

**Scenario 4 — Hyphenated compound (undesired match):**

Text:  "...the Co-Landlord shall..."  
             ^^^^^^^^^^^  
             Co-Landlord (pos 400–411)  
                ^^^^^^^^  
                ✗ "Landlord" should NOT match inside the hyphenated compound

The automaton fires for "landlord" ending at position 411\. Boundary validation rejects: the start position of "Landlord" is NOT in `word_starts` because the preceding character "-" is a word character (hyphens count as word characters in `compute_word_boundaries`). "Co-Landlord" is one word — "Landlord" cannot start mid-word. **Correctly rejected.**

**Summary:**

| Scenario | Automaton Fires? | Boundary Valid? | Result |
| ----- | ----- | ----- | ----- |
| "Contract" in "Breach of Contract" | ✓ | ✓ start at word boundary | **Match** (nested concept) |
| "Contract" in "Subcontractor" | ✓ | ✗ start NOT at word boundary | **Reject** (substring collision) |
| "Contract" \+ "Contract Law" \+ "Law" | ✓ ✓ ✓ | ✓ ✓ ✓ | **All match** (compound concepts) |
| "Landlord" in "Co-Landlord" | ✓ | ✗ start NOT at word boundary | **Reject** (hyphenated compound) |

#### **6.6.7 Annotation Output Structure for Overlapping Spans**

Overlapping annotations coexist in a flat array — no hierarchical nesting in the data model. Each annotation stands alone with its own `start`, `end`, `text`, `iri`, and `branch`:

\[  
  {  
    "id": "ann\_088",  
    "start": 100, "end": 119,  
    "text": "Breach of Contract",  
    "iri": "folio:LitClaim\_BoC\_001",  
    "label": "Breach of Contract",  
    "branch": "Litigation Claims"  
  },  
  {  
    "id": "ann\_089",  
    "start": 111, "end": 119,  
    "text": "Contract",  
    "iri": "folio:DocArt\_Contract\_001",  
    "label": "Contract",  
    "branch": "Document Artifacts"  
  }  
\]

Annotations `ann_088` and `ann_089` overlap: the range 111–119 belongs to both. Any consumer can detect containment or overlap by comparing `[start, end]` ranges. The pipeline does not record explicit containment edges (e.g., `contained_in: "ann_088"`) because the relationship is fully derivable from the offsets. Future versions may add explicit edges for systems that benefit from pre-computed relationships.

#### **6.6.8 Impact on Export Formats**

All Tier 1 export formats natively support overlapping annotations:

| Format | Overlap Handling |
| ----- | ----- |
| **JSON** | Flat array — overlapping annotations coexist as independent objects |
| **W3C JSON-LD** | Each annotation is a separate `Annotation` object with its own `TextPositionSelector` — overlaps are standard |
| **XML standoff** | Each `<annotation>` element carries its own start/end — no nesting constraint |
| **CSV** | One row per annotation — overlapping ranges appear as separate rows |
| **JSONL** | One line per annotation — overlapping ranges appear as separate lines |
| **RDF/Turtle** | Each annotation is an independent triple set — overlaps are natural |
| **brat standoff** | Each `T` line is independent — brat explicitly supports overlapping spans |
| **HTML inline** | Nested `<span>` tags: `<span data-branch="Litigation Claims">Breach of <span data-branch="Document Artifacts">Contract</span></span>` — valid HTML; requires careful CSS layering |

---

### **6.7 Stage 6.5: Context-Aware Branch Disambiguation (Judge LLM)**

#### **6.7.1 The Problem**

Stage 4 instructs the LLM to over-include branches — "United States" gets tagged as both "Locations" and "Governmental Bodies." Stage 5 confirms that FOLIO contains valid concepts in both branches. Stage 6 stamps both annotations onto every occurrence. But in a specific sentence, only one branch may be semantically correct:

Sentence A: "The person flew to the United States."  
  → "United States" \= Location ✓, Governmental Body ✗

Sentence B: "The United States negotiated a peace treaty."  
  → "United States" \= Governmental Body ✓, Location ✗

Sentence C: "The United States, located in North America, signed the accord."  
  → "United States" \= Location ✓, Governmental Body ✓

Without contextual disambiguation, the pipeline produces correct-but-noisy output: every occurrence of "United States" carries both branch annotations, even where only one applies. For single-branch concepts like "Landlord" (always "Actors"), this stage has nothing to do. For multi-branch concepts, the Judge earns its keep.

#### **6.7.2 When the Judge Fires**

The Judge stage activates **only for multi-branch concepts** — concepts where the resolution cache contains 2+ resolved branches for the same text. Single-branch concepts pass through untouched.

**Per-chunk execution for progressive rendering:** The Branch Judge runs per-chunk as annotations arrive, not after the full document completes. Each chunk's multi-branch annotations go to the Judge immediately. The Judge's context window (§6.7.3) contains surrounding text from the canonical text at that occurrence — the Judge does not need the full document to decide whether "United States" at position 5,000 functions as a location or a governmental body. The surrounding sentence provides sufficient context.

This per-chunk design means the user sees fully disambiguated annotations as each chunk completes — no "pending review" indicators, no deferred verdicts. The Judge's cost increases slightly (per-chunk batches vs. per-document batches — see §6.7.6), but the UX improvement justifies the tradeoff.

def identify\_ambiguous\_concepts(resolution\_cache: dict) \-\> set:  
    """  
    Find concepts that resolved successfully in multiple branches.  
    Only these need contextual disambiguation by the Judge.  
    """  
    \# Group resolved entries by concept text  
    resolved\_by\_text \= {}  
    for (text\_lower, branch), resolution in resolution\_cache.items():  
        if resolution\["resolved"\]:  
            resolved\_by\_text.setdefault(text\_lower, \[\]).append(branch)

    \# Return concepts with 2+ resolved branches  
    return {  
        text for text, branches in resolved\_by\_text.items()  
        if len(branches) \>= 2  
    }

For a typical 90-page lease, \~40 unique concepts might include \~5–8 ambiguous ones ("United States," "Premises," "Term," "Party," "State of New York," "force majeure," "governing law"). Only these \~5–8 concepts trigger Judge calls.

#### **6.7.3 Context Window Extraction**

For each occurrence of an ambiguous concept, the pipeline extracts a **context window** — the surrounding text from the canonical text. The window provides the Judge enough context to disambiguate without sending the entire document. Sentence boundaries are detected using **NuPunkt-RS** (§6.3.4) to preserve legal citation integrity — a naive period-based snap would break at "F." or "Cir." inside citations.

from app.services.sentence\_detector import detect\_sentences

def extract\_context\_window(canonical\_text: str, start: int, end: int,  
                           window\_chars: int \= 500,  
                           sentence\_spans: list \= None) \-\> dict:  
    """  
    Extract surrounding text for a specific occurrence.  
    Returns the concept in context plus the sentence containing it.  
      
    Window strategy:  
      1\. Expand outward from the concept by window\_chars in each direction  
      2\. Snap to NuPunkt-RS sentence boundaries (preserves citations)  
      3\. Return the context plus a marker showing where the concept sits  
      
    The sentence\_spans parameter is pre-computed once per document  
    using NuPunkt-RS and reused for all context extractions.  
    """  
    if sentence\_spans is None:  
        sentence\_spans \= detect\_sentences(canonical\_text)

    \# Expand to window boundaries  
    ctx\_start \= max(0, start \- window\_chars)  
    ctx\_end \= min(len(canonical\_text), end \+ window\_chars)

    \# Snap to NuPunkt-RS sentence boundaries  
    \# Find the sentence that contains ctx\_start; snap to its beginning  
    for sent\_start, sent\_end in sentence\_spans:  
        if sent\_start \<= ctx\_start \< sent\_end:  
            ctx\_start \= sent\_start  
            break

    \# Find the sentence that contains ctx\_end; snap to its end  
    for sent\_start, sent\_end in sentence\_spans:  
        if sent\_start \< ctx\_end \<= sent\_end:  
            ctx\_end \= sent\_end  
            break

    context\_text \= canonical\_text\[ctx\_start:ctx\_end\].strip()

    \# Mark the concept position within the context  
    local\_start \= start \- ctx\_start  
    local\_end \= end \- ctx\_start

    return {  
        "context\_text": context\_text,  
        "concept\_start\_in\_context": local\_start,  
        "concept\_end\_in\_context": local\_end,  
        "concept\_text": canonical\_text\[start:end\],  
    }

#### **6.7.4 Judge LLM Prompt**

The Judge receives the concept, the candidate branches (each with its FOLIO definition), and the surrounding context. It returns a verdict for each branch: **keep** or **reject**.

SYSTEM:  
You are a legal concept disambiguator. Given a legal concept found  
in a document, its surrounding context, and candidate FOLIO ontology  
branches, determine which branches correctly describe how the concept  
is USED in this specific context.

USER:  
CONCEPT: "United States"  
CONTEXT:  
"""  
...treaty obligations under international law. The United States  
negotiated a peace treaty with the allied nations, establishing  
new diplomatic protocols for...  
"""

CANDIDATE BRANCHES:  
1\. Locations (FOLIO definition: "A geographical place or region")  
2\. Governmental Bodies (FOLIO definition: "An entity that exercises  
   governmental authority")

TASK: For each candidate branch, determine whether it correctly  
describes how "United States" functions IN THIS SPECIFIC CONTEXT.  
A concept may legitimately belong to multiple branches in the same  
context (e.g., "The United States, located in North America, signed  
the accord" → both Location and Governmental Body apply).

OUTPUT FORMAT (JSON array, nothing else):  
\[  
  {"branch": "Locations", "keep": false,  
   "reason": "Used as an actor negotiating a treaty, not as a place"},  
  {"branch": "Governmental Bodies", "keep": true,  
   "reason": "Functions as a sovereign entity taking diplomatic action"}  
\]

RULES:  
1\. Judge based on HOW the concept functions in context, not what  
   it theoretically could mean.  
2\. Keep a branch if the context supports that meaning, even partially.  
3\. When in doubt, KEEP the branch — err toward preserving annotations.  
4\. Return a judgment for EVERY candidate branch.

#### **6.7.5 Embedding Triage \+ Batching for Efficiency**

**Embedding triage (pre-filter):** Before sending occurrences to the LLM Judge, the pipeline applies embedding-based triage — the same pattern used in Reconciliation triage (§6.4A.5). For each occurrence of a multi-branch concept, embed the surrounding sentence and compute cosine similarity against each candidate branch's FOLIO definition:

* If similarity clearly favors one branch (e.g., 0.91 for "Locations" vs. 0.35 for "Governmental Bodies"), auto-resolve without an LLM call.  
* If similarities are close (e.g., 0.72 vs. 0.68), send to the LLM Judge.

This auto-resolves \~30–50% of Branch Judge occurrences. "Flew to the United States" clearly favors Locations. "The United States enacted legislation" clearly favors Governmental Bodies. "The United States, located in North America, signed the accord" is ambiguous — send to Judge.

**Batching (for remaining occurrences):** Rather than one LLM call per occurrence, the Judge batches multiple occurrences of the same ambiguous concept into a single prompt. Each occurrence gets its own context snippet:

CONCEPT: "United States"  
CANDIDATE BRANCHES: Locations, Governmental Bodies

OCCURRENCE 1 (offset 28910):  
"""...The person flew to the United States last Tuesday..."""

OCCURRENCE 2 (offset 45220):  
"""...The United States negotiated a peace treaty..."""

OCCURRENCE 3 (offset 62100):  
"""...in the United States, located in North America, the court..."""

For each occurrence, judge each branch. Output:  
\[  
  {"occurrence": 1, "branch": "Locations", "keep": true},  
  {"occurrence": 1, "branch": "Governmental Bodies", "keep": false},  
  {"occurrence": 2, "branch": "Locations", "keep": false},  
  {"occurrence": 2, "branch": "Governmental Bodies", "keep": true},  
  {"occurrence": 3, "branch": "Locations", "keep": true},  
  {"occurrence": 3, "branch": "Governmental Bodies", "keep": true}  
\]

This batching reduces LLM calls from (occurrences × ambiguous concepts) to approximately (ambiguous concepts), since each concept's occurrences get judged together.

#### **6.7.6 Token Economics for the Judge**

| Component | Tokens | Notes |
| ----- | ----- | ----- |
| Context window per occurrence | \~200 | 500 chars ≈ 125 tokens, plus formatting |
| Branch definitions per concept | \~100 | FOLIO definitions are concise |
| Prompt template | \~200 | Fixed |
| Occurrences per batch (post-triage) | \~5–12 | Embedding triage removes obvious cases; remaining ambiguous occurrences batched |
| **Total per Judge call** | **\~1,500–3,000 input \+ \~200 output** | One call per ambiguous concept |
| **Judge calls per document** | **\~5–8** | Only multi-branch concepts trigger |
| **Total Judge cost per document** | **\~15,000–25,000 tokens** | Reduced \~30% from pre-triage estimate by embedding auto-resolution |

The Judge adds roughly 10–17% to the total LLM token cost — reduced from \~15–25% by embedding triage.

#### **6.7.7 Implementation**

\# backend/app/services/judge\_service.py (NEW)

async def run\_judge\_pass(  
    annotations: list\[dict\],  
    resolution\_cache: dict,  
    canonical\_text: str,  
    llm\_provider,  \# FOLIO Mapper's LLM abstraction  
) \-\> list\[dict\]:  
    """  
    Context-aware disambiguation for multi-branch concepts.  
      
    1\. Identify ambiguous concepts (2+ resolved branches)  
    2\. For each ambiguous concept, gather all occurrences with context  
    3\. Batch-call the Judge LLM with context windows  
    4\. Filter annotations based on Judge verdicts  
    5\. Pass through single-branch annotations untouched  
      
    FOLIO Mapper cross-reference:  
      \- LLM provider abstraction: backend/app/services/llm/  
      \- Judge validation pattern: backend/app/services/pipeline/  
        (Stage 3 in FOLIO Mapper's existing mapping pipeline)  
    """  
    ambiguous \= identify\_ambiguous\_concepts(resolution\_cache)

    if not ambiguous:  
        return annotations  \# nothing to judge

    \# Partition annotations  
    needs\_judging \= \[a for a in annotations  
                     if a\["text"\].lower() in ambiguous\]  
    pass\_through \= \[a for a in annotations  
                    if a\["text"\].lower() not in ambiguous\]

    \# Group ambiguous annotations by concept text  
    by\_concept \= {}  
    for ann in needs\_judging:  
        key \= ann\["text"\].lower()  
        by\_concept.setdefault(key, \[\]).append(ann)

    judged \= \[\]  
    for concept\_text, occurrences in by\_concept.items():  
        \# Collect resolved branches for this concept  
        branches\_with\_defs \= \[\]  
        for (text\_lower, branch), res in resolution\_cache.items():  
            if text\_lower \== concept\_text and res\["resolved"\]:  
                branches\_with\_defs.append({  
                    "branch": branch,  
                    "folio\_label": res\["label"\],  
                    "folio\_definition": res.get("definition", ""),  
                })

        \# Extract context windows for each occurrence  
        occurrence\_contexts \= \[\]  
        for i, ann in enumerate(occurrences):  
            ctx \= extract\_context\_window(  
                canonical\_text, ann\["start"\], ann\["end"\]  
            )  
            occurrence\_contexts.append({  
                "occurrence\_index": i,  
                "offset": ann\["start"\],  
                "context": ctx\["context\_text"\],  
                "branch": ann\["branch"\],  
            })

        \# Batch by concept: all occurrences in one LLM call  
        verdicts \= await call\_judge\_llm(  
            concept\_text=concept\_text,  
            branches=branches\_with\_defs,  
            occurrences=occurrence\_contexts,  
            llm\_provider=llm\_provider,  
        )

        \# Apply verdicts: keep or reject each annotation  
        for ann in occurrences:  
            verdict \= find\_verdict(  
                verdicts, ann\["start"\], ann\["branch"\]  
            )  
            if verdict is None or verdict.get("keep", True):  
                \# No verdict found or Judge says keep → preserve  
                ann\["judge\_verdict"\] \= "kept"  
                judged.append(ann)  
            else:  
                \# Judge says reject → discard, but log  
                ann\["judge\_verdict"\] \= "rejected"  
                ann\["judge\_reason"\] \= verdict.get("reason", "")  
                \# Optionally store in a "judge\_rejected" array  
                \# for debugging and prompt tuning

    return pass\_through \+ judged

#### **6.7.8 Fallback Behavior**

| Scenario | What Happens |
| ----- | ----- |
| Judge LLM unavailable or times out | All multi-branch annotations pass through unfiltered (same as before this stage existed) |
| Judge returns ambiguous verdict | Keep the annotation (err toward inclusion) |
| Judge rejects all branches for an occurrence | Keep at least the highest-confidence branch (never leave an occurrence with zero annotations) |
| Single-branch concept | Bypasses Judge entirely — no LLM call |

#### **6.7.9 FOLIO Mapper Cross-Reference**

This stage directly parallels **FOLIO Mapper's Stage 3 — Judge validation** (`backend/app/services/pipeline/`), which reviews mapping candidates, adjusts scores, and rejects false positives. The annotation pipeline's Judge uses the same LLM provider infrastructure and follows the same review-and-filter pattern. Key differences:

| Aspect | FOLIO Mapper's Stage 3 | Annotation Pipeline's Judge |
| ----- | ----- | ----- |
| **Input** | Candidate FOLIO concepts for a taxonomy term | Candidate branches for a document span |
| **Context** | The taxonomy term's label and hierarchy | The document's surrounding sentences |
| **Decision** | Adjust confidence score; reject low-confidence | Keep or reject each branch per occurrence |
| **Granularity** | Per taxonomy term | Per occurrence in the document |
| **LLM provider** | Same abstraction (`backend/app/services/llm/`) | Same abstraction |

The new Judge service should live at `backend/app/services/judge_service.py` and import the LLM provider from `backend/app/services/llm/`.

---

### **6.8A Stage 6.75: Syntactic Relation Extraction (spaCy Dependency Parsing)**

#### **6.8A.1 Purpose — From Span Annotations to Knowledge Graph Triples**

Stages 1–6.5 produce span annotations: each text span tagged with a FOLIO IRI, branch, and definition. These annotations identify the *vocabulary* of the knowledge graph — nodes and edge labels. But a knowledge graph needs *structure*: which nodes connect via which edges.

FOLIO includes verbs as ontology concepts: "denied," "overruled," "drafted," "signed," "terminated." When two or more FOLIO concepts co-occur in a sentence, the syntactic structure reveals their relationships:

"The court denied the motion."  
  Subject: "court"   (folio:Court)        → graph node  
  Predicate: "denied" (folio:Denied)      → graph edge  
  Object: "motion"   (folio:Motion)       → graph node

Triple: folio:Court → folio:Denied → folio:Motion

The dependency parser extracts these Subject-Predicate-Object (SPO) triples deterministically from the sentence's syntactic tree. No LLM involved — pure structural analysis.

#### **6.8A.2 When Dependency Parsing Fires**

The parser processes only sentences that contain **two or more annotated FOLIO concepts** where at least one concept is a FOLIO verb. Sentences with zero or one concept produce no triples. Sentences with only nouns (no FOLIO verb) produce no triples — the relationship between them is unknown without a predicate.

For a 100-page contract, roughly 20–30% of sentences contain 2+ annotated concepts with at least one FOLIO verb. The parsing cost targets only those sentences.

**How `folio_verbs` is built:** At startup, the pipeline walks the FOLIO ontology tree and collects every concept under the **Events** branch whose label is a verb form (e.g., "denied," "overruled," "drafted," "signed," "filed," "appealed"). Specifically:

1. Load the FOLIO ontology JSON (same source used by the EntityRuler pattern loader).
2. Filter to concepts whose top-level branch is `Events` (IRI prefix `folio:Events/`).
3. For each matching concept, test whether its label's lemma (via spaCy) has a `VB*` POS tag.
4. Collect the lowercased labels into a `frozenset[str]` stored as `folio_verbs` on the shared `PipelineContext`.

This set is computed once at startup and passed to `extract_relations()`. Typical size: ~200–400 verb concepts.

#### **6.8A.3 Sentence Segmentation**

The dependency parser needs sentence boundaries. It uses NuPunkt-RS (§6.3.4) to segment the canonical text into sentences, preserving citation integrity. The sentence spans are cached and reused from the chunking stage if available.

#### **6.8A.4 Implementation**

\# backend/app/services/relation\_extractor.py (NEW)

import spacy  
from nupunkt import sent\_tokenize

def extract\_relations(  
    canonical\_text: str,  
    annotations: list\[dict\],  
    folio\_verbs: set\[str\],  
) \-\> list\[dict\]:  
    """  
    Extract SPO triples from sentences containing 2+ FOLIO concepts.  
      
    Uses spaCy dependency parsing to identify syntactic roles:  
      nsubj → Subject  
      ROOT verb → Predicate  
      dobj / pobj / attr → Object  
      
    Only fires on sentences where at least one annotation is a  
    FOLIO verb (e.g., "denied," "overruled," "drafted").  
    """  
    nlp \= spacy.load("en\_core\_web\_trf")

    \# Segment canonical text into sentences using NuPunkt-RS  
    sentences \= sent\_tokenize(canonical\_text)  
    sentence\_spans \= \[\]  
    offset \= 0  
    for sent in sentences:  
        start \= canonical\_text.index(sent, offset)  
        sentence\_spans.append((start, start \+ len(sent), sent))  
        offset \= start \+ len(sent)

    \# Index annotations by character position for fast lookup  
    from intervaltree import IntervalTree  
    ann\_tree \= IntervalTree()  
    for ann in annotations:  
        ann\_tree.addi(ann\["start"\], ann\["end"\], ann)

    triples \= \[\]

    for sent\_start, sent\_end, sent\_text in sentence\_spans:  
        \# Find all annotations within this sentence  
        overlapping \= ann\_tree.overlap(sent\_start, sent\_end)  
        sent\_annotations \= \[iv.data for iv in overlapping\]

        if len(sent\_annotations) \< 2:  
            continue

        \# Check for at least one FOLIO verb  
        has\_verb \= any(  
            a\["label"\].lower() in folio\_verbs  
            for a in sent\_annotations  
        )  
        if not has\_verb:  
            continue

        \# Parse sentence with spaCy  
        doc \= nlp(sent\_text)

        \# Extract SPO patterns via dependency tree  
        for token in doc:  
            if token.dep\_ \== "ROOT" and token.pos\_ \== "VERB":  
                verb\_text \= token.lemma\_.lower()

                \# Find subject (nsubj)  
                subjects \= \[  
                    child for child in token.children  
                    if child.dep\_ in ("nsubj", "nsubjpass")  
                \]

                \# Find objects (dobj, pobj, attr)  
                objects \= \[  
                    child for child in token.children  
                    if child.dep\_ in ("dobj", "pobj", "attr")  
                \]

                \# Also check prepositional objects  
                for child in token.children:  
                    if child.dep\_ \== "prep":  
                        for grandchild in child.children:  
                            if grandchild.dep\_ \== "pobj":  
                                objects.append(grandchild)

                \# Match subjects and objects to FOLIO annotations  
                for subj\_token in subjects:  
                    subj\_ann \= match\_token\_to\_annotation(  
                        subj\_token, sent\_start, sent\_annotations  
                    )  
                    if not subj\_ann:  
                        continue

                    \# Match verb to FOLIO annotation if it's a FOLIO verb  
                    verb\_ann \= match\_token\_to\_annotation(  
                        token, sent\_start, sent\_annotations  
                    )  
                    predicate\_iri \= (  
                        verb\_ann\["iri"\] if verb\_ann  
                        else f"http://folio.openlegalstandard.org/predicate/{verb\_text}"  
                    )

                    for obj\_token in objects:  
                        obj\_ann \= match\_token\_to\_annotation(  
                            obj\_token, sent\_start, sent\_annotations  
                        )  
                        if not obj\_ann:  
                            continue

                        triples.append({  
                            "subject": {  
                                "text": subj\_ann\["text"\],  
                                "iri": subj\_ann\["iri"\],  
                                "label": subj\_ann\["label"\],  
                                "branch": subj\_ann\["branch"\],  
                            },  
                            "predicate": {  
                                "text": token.text,  
                                "lemma": verb\_text,  
                                "iri": predicate\_iri,  
                            },  
                            "object": {  
                                "text": obj\_ann\["text"\],  
                                "iri": obj\_ann\["iri"\],  
                                "label": obj\_ann\["label"\],  
                                "branch": obj\_ann\["branch"\],  
                            },  
                            "sentence": sent\_text,  
                            "sentence\_start": sent\_start,  
                            "sentence\_end": sent\_end,  
                            "extraction\_method": "dependency\_parse",  
                        })

    return triples

def match\_token\_to\_annotation(  
    token, sent\_start: int, sent\_annotations: list\[dict\]  
) \-\> dict | None:  
    """  
    Match a spaCy token (or its head span) to a FOLIO annotation.  
    Expands the token to its full noun phrase if needed.  
    """  
    \# Compute token's global position  
    token\_global\_start \= sent\_start \+ token.idx  
    token\_global\_end \= token\_global\_start \+ len(token.text)

    \# Try exact match first  
    for ann in sent\_annotations:  
        if ann\["start"\] \<= token\_global\_start and token\_global\_end \<= ann\["end"\]:  
            return ann

    \# Try expanding to the full subtree (noun phrase)  
    subtree\_start \= sent\_start \+ min(t.idx for t in token.subtree)  
    subtree\_end \= sent\_start \+ max(t.idx \+ len(t.text) for t in token.subtree)

    for ann in sent\_annotations:  
        \# Check if annotation overlaps with the subtree  
        if ann\["start"\] \< subtree\_end and subtree\_start \< ann\["end"\]:  
            return ann

    return None

#### **6.8A.5 Triple Output Schema**

{  
  "triples": \[  
    {  
      "subject": {  
        "text": "The court",  
        "iri": "folio:Court\_SDNY\_001",  
        "label": "District Court, S.D. New York",  
        "branch": "Governmental Bodies"  
      },  
      "predicate": {  
        "text": "denied",  
        "lemma": "deny",  
        "iri": "folio:Event\_Denied\_001"  
      },  
      "object": {  
        "text": "the motion",  
        "iri": "folio:DocArt\_Motion\_001",  
        "label": "Motion",  
        "branch": "Document Artifacts"  
      },  
      "sentence": "The court denied the motion for summary judgment.",  
      "sentence\_start": 45200,  
      "sentence\_end": 45249,  
      "extraction\_method": "dependency\_parse"  
    }  
  \]  
}

#### **6.8A.6 Triple Validation**

Not every syntactic SPO pattern produces a valid knowledge graph triple. The pipeline validates each candidate triple against FOLIO's ontology constraints:

1. **Domain check:** Does the subject's FOLIO class belong to the domain of the predicate? (e.g., "Court" is a valid agent of "denied")  
2. **Range check:** Does the object's FOLIO class belong to the range of the predicate? (e.g., "Motion" is a valid patient of "denied")  
3. **Self-reference check:** Subject and object must resolve to different entities (reject loops)

Invalid triples get logged for pipeline tuning but do not enter the knowledge graph.

#### **6.8A.7 Performance**

| Document | Sentences with 2+ Concepts \+ FOLIO Verb | spaCy Parse Time | Triple Count |
| ----- | ----- | ----- | ----- |
| 30-page lease | \~50 sentences | \~2 sec | \~30–60 triples |
| 100-page M\&A agreement | \~200 sentences | \~8 sec | \~120–250 triples |
| 500-page regulatory filing | \~800 sentences | \~30 sec | \~500–1,000 triples |

spaCy's `en_core_web_trf` (transformer-backed) processes \~25 sentences/sec. For a 100-page document, dependency parsing adds \~8 seconds — negligible compared to LLM processing time. The `en_core_web_sm` model offers \~200 sentences/sec with slightly reduced accuracy.

---

### **6.8 Stage 7: Annotation \+ Triple Persistence and Delivery**

#### **6.8.1 JSON Annotation Schema**

{  
  "document\_id": "contract\_2026\_001.pdf",  
  "source\_format": "pdf",  
  "canonical\_text\_hash": "sha256:a1b2c3d4...",  
  "pipeline\_version": "5.0.0",  
  "processed\_at": "2026-02-21T14:30:00Z",

  "document\_metadata": {  
    "filename": "Acme\_v\_Smith\_MTD.pdf",  
    "file\_size\_bytes": 245000,  
    "page\_count": 32,  
    "canonical\_text\_length": 128000,

    "document\_type": {  
      "folio\_label": "Motion to Dismiss",  
      "folio\_iri": "folio:DocArt\_MTD\_001",  
      "folio\_branch\_path": \["Document Artifacts", "Motions", "Dispositive Motions", "Motion to Dismiss"\],  
      "confidence": 0.95,  
      "evidence": "Title reads 'DEFENDANT'S MOTION TO DISMISS'; filename 'mtd\_12b6\_final.pdf' corroborates",  
      "filename\_hint": {"hint": "Motion to Dismiss", "matched\_token": "mtd", "source": "filename\_abbreviation"}  
    },  
    "document\_subtype": {  
      "folio\_label": "Motion to Dismiss for Failure to State a Claim",  
      "folio\_iri": "folio:DocArt\_MTD\_FRCP12b6\_001",  
      "confidence": 0.88  
    },  
    "attachments": \[  
      {  
        "label": "Exhibit A",  
        "document\_type": {"folio\_label": "Employment Agreement", "folio\_iri": "folio:DocArt\_EmpAgmt\_001"},  
        "boundary\_marker": "EXHIBIT A",  
        "start\_page": 12,  
        "start\_char": 45000,  
        "end\_char": 62000  
      }  
    \],

    "case\_information": {  
      "case\_number": "Case No. 1:2025-cv-01234-ABC",  
      "docket\_number": "Dkt. No. 45",  
      "case\_caption": "Acme Corporation v. John Smith",  
      "filing\_date": "2025-03-15",  
      "document\_date": "2025-03-10"  
    },

    "court": {  
      "name": "United States District Court, Southern District of New York",  
      "folio\_iri": "folio:Gov\_SDNY\_001",  
      "court\_level": "Federal District Court",  
      "jurisdiction\_type": "Federal",  
      "state": "New York",  
      "district": "Southern"  
    },

    "judge": {"name": "Hon. Sarah Chen", "title": "United States District Judge"},  
    "panel": null,

    "parties": \[  
      {  
        "name": "Acme Corporation",  
        "role": "Plaintiff",  
        "party\_type": "Corporation",  
        "folio\_actor\_type": "folio:Actors\_Corporation\_001",  
        "counsel": \[  
          {"name": "Jane Doe", "bar\_number": "NY-123456", "firm": "Smith & Associates"}  
        \]  
      },  
      {  
        "name": "John Smith",  
        "role": "Defendant",  
        "party\_type": "Individual",  
        "folio\_actor\_type": "folio:Actors\_Individual\_001",  
        "counsel": \[  
          {"name": "Robert Lee", "bar\_number": "NY-789012", "firm": "Lee Legal Group"}  
        \]  
      }  
    \],

    "signatories": \[  
      {"name": "Robert Johnson", "title": "CEO", "organization": "Acme Corporation", "extraction\_method": "annotation\_promotion"}  
    \],

    "contract\_terms": {  
      "effective\_date": "2025-04-01",  
      "termination\_date": "2027-03-31",  
      "governing\_law": {"jurisdiction": "State of Delaware", "folio\_iri": "folio:Loc\_Delaware\_001"},  
      "venue": {"forum": "Southern District of New York", "folio\_iri": "folio:Gov\_SDNY\_001"}  
    },

    "litigation\_fields": {  
      "claim\_types": \[  
        {"claim": "Breach of Contract", "folio\_iri": "folio:AoL\_BreachK\_001", "count\_number": 1},  
        {"claim": "Fraud", "folio\_iri": "folio:AoL\_Fraud\_001", "count\_number": 2, "statute": "N.Y. Gen. Bus. Law § 349"}  
      \],  
      "relief\_sought": \["Compensatory Damages", "Punitive Damages", "Injunctive Relief"\],  
      "outcome": {"disposition": "Granted in part, denied in part", "date": "2025-06-20"}  
    },

    "concept\_summary": {  
      "annotations\_by\_branch": {  
        "Actors": 89, "Document Artifacts": 67, "Engagement Terms": 54,  
        "Area of Law": 43, "Contractual Clause": 38, "Events": 35  
      },  
      "top\_concepts": \[  
        {"label": "Landlord", "iri": "folio:R8pNPutX0TN6DlEqkyZuxSw", "count": 47},  
        {"label": "Premises", "iri": "folio:...", "count": 38},  
        {"label": "Tenant", "iri": "folio:...", "count": 35}  
      \],  
      "top\_cooccurrence\_pairs": \[  
        {"concept\_a": "Landlord", "concept\_b": "Tenant", "shared\_sentences": 28},  
        {"concept\_a": "Default", "concept\_b": "Termination", "shared\_sentences": 12}  
      \],  
      "top\_triples": \[  
        {"subject": "Landlord", "predicate": "may terminate", "object": "Lease", "count": 4}  
      \]  
    },

    "extraction\_provenance": {  
      "metadata\_judge\_model": "claude-sonnet-4-20250514",  
      "metadata\_judge\_calls": 4,  
      "metadata\_judge\_tokens": 12000,  
      "annotation\_promotions": 8  
    }  
  },

  "statistics": {  
    "total\_chunks": 47,  
    "unique\_concepts\_identified": 43,  
    "unique\_concept\_branch\_pairs": 60,  
    "pairs\_resolved": 45,  
    "pairs\_discarded\_no\_match": 15,  
    "total\_occurrences\_annotated": 512,  
    "folio\_resolution\_calls": 60,  
    "unresolved\_concepts": 5,  
    "entity\_ruler\_matches": 480,  
    "llm\_concepts": 80,  
    "reconciliation\_conflicts\_judged": 35,  
    "triples\_extracted": 185  
  },  
  "resolution\_cache": \[  
    {  
      "concept\_text": "Landlord",  
      "branch": "Actors",  
      "iri": "folio:R8pNPutX0TN6DlEqkyZuxSw",  
      "label": "Landlord",  
      "definition": "A party that owns and leases real property...",  
      "match\_type": "exact",  
      "discovery\_source": "both",  
      "occurrences\_in\_document": 47  
    },  
    {  
      "concept\_text": "denied",  
      "branch": "Events",  
      "iri": "folio:Event\_Denied\_001",  
      "label": "Denied",  
      "definition": "A judicial action rejecting a motion or request...",  
      "match\_type": "exact",  
      "discovery\_source": "both",  
      "occurrences\_in\_document": 8  
    },  
    {  
      "concept\_text": "the agreement",  
      "branch": "Document Artifacts",  
      "iri": "folio:DocArt\_Contract\_001",  
      "label": "Contract",  
      "definition": "A legally enforceable agreement...",  
      "match\_type": "fuzzy",  
      "discovery\_source": "llm",  
      "occurrences\_in\_document": 23  
    }  
  \],  
  "annotations": \[  
    {  
      "id": "ann\_001",  
      "start": 10452,  
      "end": 10460,  
      "text": "Landlord",  
      "iri": "folio:R8pNPutX0TN6DlEqkyZuxSw",  
      "label": "Landlord",  
      "definition": "A party that owns and leases real property...",  
      "branch": "Actors",  
      "match\_type": "exact",  
      "discovery\_source": "both",  
      "confidence\_tier": "high",  
      "state": "confirmed",  
      "provenance": {  
        "page": 14,  
        "section\_path": "Article II \> §2.3(a)",  
        "element\_type": "paragraph"  
      }  
    },  
    {  
      "id": "ann\_055",  
      "start": 120,  
      "end": 128,  
      "text": "Interest",  
      "iri": "folio:EngTerms\_AccInt",  
      "label": "Accrued Interest",  
      "definition": "Interest that has been earned but not yet paid...",  
      "branch": "Engagement Terms",  
      "match\_type": "user\_selected",  
      "discovery\_source": "entity\_ruler",  
      "confidence\_tier": "low",  
      "state": "confirmed",  
      "reconciliation\_category": "D",  
      "judge\_verdict": "rejected",  
      "judge\_reason": "Common English usage — not a legal concept in this context",  
      "user\_override": true,  
      "user\_override\_selection": {  
        "selected\_iri": "folio:EngTerms\_AccInt",  
        "selected\_label": "Accrued Interest",  
        "selection\_source": "panel\_a\_drill\_down",  
        "entity\_ruler\_original": {  
          "iri": "folio:EngTerms\_Interest\_001",  
          "label": "Interest"  
        },  
        "judge\_recommendation": {  
          "iri": "folio:EngTerms\_IntRate\_001",  
          "label": "Interest Rate",  
          "reason": "Context suggests rate-based financial term"  
        }  
      },  
      "provenance": {  
        "page": 3,  
        "section\_path": "Article IV \> §4.2(b)",  
        "element\_type": "paragraph"  
      }  
    }  
  \],  
  "triples": \[  
    {  
      "id": "triple\_001",  
      "subject": {  
        "text": "The court",  
        "iri": "folio:Court\_SDNY\_001",  
        "label": "District Court, S.D. New York",  
        "branch": "Governmental Bodies"  
      },  
      "predicate": {  
        "text": "denied",  
        "lemma": "deny",  
        "iri": "folio:Event\_Denied\_001"  
      },  
      "object": {  
        "text": "the motion",  
        "iri": "folio:DocArt\_Motion\_001",  
        "label": "Motion",  
        "branch": "Document Artifacts"  
      },  
      "sentence": "The court denied the motion for summary judgment.",  
      "sentence\_start": 45200,  
      "sentence\_end": 45249,  
      "extraction\_method": "dependency\_parse"  
    }  
  \],  
  "unresolved": \[  
    {  
      "concept\_text": "anti-assignment provision",  
      "branches\_attempted": \["Contractual Clause"\],  
      "flag": "no\_folio\_match",  
      "chunks\_identified\_in": \["chunk\_22100", "chunk\_24500"\]  
    }  
  \]  
}

Note: Each annotation carries:

* `state`: `"preliminary"` (awaiting confirmation), `"confirmed"` (pipeline verified or user resurrected), or `"rejected"` (Judge disagreed — visible but dimmed in the UI, user can resurrect)  
* `discovery_source`: `"both"` (EntityRuler \+ LLM agreed), `"llm"` (contextual discovery), `"entity_ruler"` (EntityRuler found, Judge confirmed), or `"reconciliation_judge"` (conflict resolved by Judge)  
* `confidence_tier`: `"high"` (multi-word or legal-specific label) or `"low"` (common English word matching FOLIO label)  
* `user_override`: `true` if the user resurrected a rejected annotation; includes `user_override_selection` with full provenance (EntityRuler original, Judge recommendation, user's selection, and which panel they selected from)

The `triples` array carries SPO triples extracted by the dependency parser (§6.8A).

#### **6.8.2 Frontend Rendering Requirements**

1. Display the document text with annotated spans highlighted in one of three visual states (see §6.4A.8):  
   * **Preliminary:** lighter highlight \+ uncertainty indicator (dotted border, "?" badge, reduced opacity for low-confidence)  
   * **Confirmed:** full highlight, branch-colored, solid border  
   * **Rejected:** very faint highlight or strikethrough; dimmed but visible; "Resurrect" affordance  
2. On click/tap of a confirmed annotation, show a tooltip or panel: FOLIO label, definition, IRI, branch, ontology path, ancestry tree  
3. On hover of a rejected annotation, show the Judge's rejection reason. On click, offer "Resurrect" button that opens the dual-panel concept selection workflow (§6.8.4)  
4. **"Hide uncertain" toggle** in the toolbar switches between "Show all" (default — preliminary \+ confirmed \+ rejected) and "Show confirmed only." Toggle persists per session.  
5. **Support stacked annotations at the same span.** When a concept resolves to multiple branches (e.g., "United States" as both a Location and a Governmental Body), display all annotations for that span. The tooltip/panel groups them by branch with FOLIO Mapper's branch color coding (`packages/core/src/folio/`).  
6. **Support overlapping and nested spans.** When a user clicks on "Contract" within the phrase "Breach of Contract," the tooltip displays *both* annotations: "Contract" as a Document Artifact *and* "Breach of Contract" as a Litigation Claim. The frontend computes which annotations contain the clicked character position by checking `start <= click_position < end` across all annotations.  
7. **Layered highlighting for overlapping spans.** Nested annotations render as layered highlights using CSS gradients, borders, or opacity stacking. The outermost concept (longest span) gets the base highlight; inner concepts get a secondary indicator (underline, darker shade, or dotted border). Branch colors differentiate the layers.  
8. Provide a sidebar listing all unique concepts grouped by branch, with occurrence counts and links to their positions. Rejected annotations appear in a separate "Rejected (review)" group with resurrection affordance.  
9. The annotation JSON layer serves as the single source of truth — the frontend performs no concept resolution  
10. **Dual-panel resurrection workflow** (§6.8.4) uses FOLIO Mapper's existing tree component for ancestry display, branch color coding, and detail endpoint integration

#### **6.8.3 Progressive Rendering via Server-Sent Events (SSE)**

The frontend receives progressive updates via an SSE stream. Annotations appear incrementally as the pipeline processes each stage. ALL EntityRuler matches display immediately — both high-confidence and low-confidence — with visual indicators communicating certainty level.

**SSE Endpoint:** `GET /api/annotate/stream/{job_id}`

**Event Types:**

event: document\_text  
data: {"text": "...", "text\_range": \[0, 50000\]}  
  → Frontend renders the document text (or a portion of it)

event: preliminary\_annotations  
data: {"source": "entity\_ruler", "annotations": \[  
    {"id": "ann\_001", ..., "confidence\_tier": "high", "state": "preliminary"},  
    {"id": "ann\_055", ..., "confidence\_tier": "low", "state": "preliminary"}  
  \]}  
  → ALL EntityRuler matches appear:  
    High-confidence: solid highlight, branch-colored  
    Low-confidence: lighter highlight \+ uncertainty indicator

event: chunk\_reconciled  
data: {"chunk\_id": "chunk\_0", "text\_range": \[0, 5000\],  
       "confirmed": \[{"id": "ann\_001", "state": "confirmed", ...}\],  
       "rejected": \[{"id": "ann\_055", "state": "rejected",  
                      "judge\_reason": "Common English usage"}\],  
       "new\_concepts": \[{"id": "ann\_080", "state": "confirmed", ...}\]}  
  → "confirmed": preliminary annotations upgrade to full highlight  
  → "rejected": annotations dim to rejected state (faint highlight,  
    strikethrough) but REMAIN VISIBLE with "Resurrect" affordance  
  → "new\_concepts": LLM-discovered contextual concepts appear as confirmed

event: judge\_update  
data: {"annotation\_id": "ann\_042", "verdict": "rejected",  
       "reason": "Context disambiguation"}  
  → Branch Judge verdicts update existing annotations

event: triples\_ready  
data: {"chunk\_range": \[0, 5000\], "triples": \[...\]}  
  → Dependency-parsed triples available for knowledge graph view

event: pipeline\_complete  
data: {"statistics": {...}, "total\_annotations": 512,  
       "total\_triples": 185}  
  → Pipeline finished. All annotations in final state:  
    confirmed, rejected-but-visible, or user-resurrected.

**"Hide uncertain" toggle:** A toolbar toggle switches between "Show all" (default — shows preliminary, confirmed, AND rejected annotations) and "Show confirmed only" (hides preliminary and rejected). The toggle persists per session. Legal professionals default to seeing everything; focused reading mode hides the noise.

#### **6.8.4 User Resurrection of Rejected Annotations**

When the Judge rejects an annotation, the rejected concept remains visible in the document with a dimmed visual treatment. The user can override the Judge by clicking "Resurrect." This launches a dual-panel concept selection workflow.

**6.8.4.1 Resurrection Trigger**

Hovering over a rejected annotation displays:

* The Judge's rejection reason (e.g., "Common English 'interest' meaning curiosity — not a legal concept in this context")  
* A "Resurrect" button

Clicking "Resurrect" opens a concept selection panel with two parallel tracks:

**6.8.4.2 Dual-Panel Concept Selection**

Two panels fire simultaneously when the user clicks "Resurrect":

**Panel A — EntityRuler's original match (immediate, zero latency):**

The EntityRuler matched the text to one or more FOLIO concepts. Panel A displays each matching concept's full ancestry tree — from root to leaf, including children and siblings — using FOLIO Mapper's existing tree component (`packages/core/src/folio/`). The tree data comes from FOLIO Mapper's detail endpoint:

POST /api/mapping/detail  
Body: {"iri": "folio:EngTerms\_Interest\_001"}  
Response: {  
  "label": "Interest",  
  "definition": "A charge for borrowed money...",  
  "ancestors": \[  
    {"iri": "folio:root", "label": "FOLIO"},  
    {"iri": "folio:EngTerms", "label": "Engagement Terms"},  
    {"iri": "folio:FinTerms", "label": "Financial Terms"},  
    {"iri": "folio:EngTerms\_Interest\_001", "label": "Interest"}  
  \],  
  "children": \[  
    {"iri": "folio:EngTerms\_SimpleInt", "label": "Simple Interest"},  
    {"iri": "folio:EngTerms\_CompInt", "label": "Compound Interest"},  
    {"iri": "folio:EngTerms\_AccInt", "label": "Accrued Interest"}  
  \],  
  "siblings": \[  
    {"iri": "folio:EngTerms\_Premium", "label": "Premium"},  
    {"iri": "folio:EngTerms\_Dividend", "label": "Dividend"}  
  \]  
}

The user can click any node in the tree — the matched leaf, a parent, a child, or a sibling — to select the concept they think best fits the context. If "Interest" is too broad, they drill down to "Accrued Interest." If the EntityRuler matched the wrong branch entirely, the ancestry path gives them a route to navigate upward and across.

If the FOLIO label maps to multiple concepts in different branches (e.g., "Interest" as a financial term AND as a property concept), Panel A displays all matching trees:

Panel A — "Interest" found in 3 FOLIO locations:

Tree 1: Engagement Terms → Financial Terms → Interest  
Tree 2: Asset Types → Financial Assets → Interest  
Tree 3: Area of Law → Property Law → Ownership Interest

Select the concept that matches this context.

FOLIO Mapper's `search_by_label()` method already returns all matching concepts across branches. The resurrection panel calls this same search.

**Panel B — Judge's contextual recommendation (arrives in 1–3 seconds):**

Simultaneously, a targeted LLM call fires:

SYSTEM:  
The user overrode a rejected annotation. They believe this text  
functions as a legal concept despite the Judge's initial rejection.  
Recommend the most specific (leaf-level) FOLIO concept that best  
fits this usage in context.

USER:  
CONCEPT TEXT: "{concept\_text}"  
CONTEXT: "...{500 chars surrounding the occurrence}..."

ENTITY RULER MATCHED: {folio\_label} ({folio\_iri}) in branch {branch}  
ORIGINAL REJECTION REASON: "{judge\_reason}"

TASK: Given that the user believes this IS a legal concept, which  
FOLIO concept best fits this specific usage? Return the most  
specific leaf-level concept. If the EntityRuler's original match  
is correct, confirm it.

OUTPUT FORMAT (JSON):  
{"recommended\_iri": "folio:...", "recommended\_label": "...",  
 "branch": "...", "reason": "..."}

When the Judge responds, Panel B renders the recommended concept's ancestry tree — using the same FOLIO Mapper tree component as Panel A. If the Judge recommends a different concept than the EntityRuler matched, Panel B shows a different tree, visually highlighting the difference:

┌─────────────────────────┐  ┌─────────────────────────┐  
│ Panel A: EntityRuler     │  │ Panel B: Judge           │  
│                          │  │ Recommends               │  
│ FOLIO                    │  │                          │  
│  └─ Engagement Terms     │  │ FOLIO                    │  
│       └─ Financial Terms │  │  └─ Asset Types          │  
│            └─ Interest ← │  │       └─ Financial Assets│  
│                 ├─ Simple │  │            └─ Interest   │  
│                 ├─ Comp.  │  │                Rate ←    │  
│                 └─ Accrued│  │                          │  
│                          │  │ "Context suggests rate-   │  
│                          │  │  based financial term"    │  
└─────────────────────────┘  └─────────────────────────┘  
              Click any node to select

If the Judge agrees with the EntityRuler, Panel B confirms the same concept — reinforcing the user's decision.

**6.8.4.3 User Selection and Provenance**

The user clicks any node from either panel. The selection becomes the final annotation with full decision provenance:

{  
  "id": "ann\_055",  
  "start": 120,  
  "end": 128,  
  "text": "Interest",  
  "iri": "folio:EngTerms\_AccInt",  
  "label": "Accrued Interest",  
  "definition": "Interest that has been earned but not yet paid...",  
  "branch": "Engagement Terms",  
  "match\_type": "user\_selected",  
  "discovery\_source": "entity\_ruler",  
  "confidence\_tier": "low",  
  "reconciliation\_category": "D",  
  "judge\_verdict": "rejected",  
  "judge\_reason": "Common English usage — 'no interest in pursuing the claim'",  
  "user\_override": true,  
  "user\_override\_selection": {  
    "selected\_iri": "folio:EngTerms\_AccInt",  
    "selected\_label": "Accrued Interest",  
    "selection\_source": "panel\_a\_drill\_down",  
    "entity\_ruler\_original": {  
      "iri": "folio:EngTerms\_Interest\_001",  
      "label": "Interest"  
    },  
    "judge\_recommendation": {  
      "iri": "folio:EngTerms\_IntRate\_001",  
      "label": "Interest Rate",  
      "reason": "Context suggests rate-based financial term"  
    }  
  },  
  "provenance": {  
    "page": 3,  
    "section\_path": "Article IV \> §4.2(b)",  
    "element\_type": "paragraph"  
  }  
}

The `user_override_selection` object captures the full decision trail: the EntityRuler's original match, the Judge's recommendation, which panel the user selected from, and the specific node they clicked. This provenance enables:

1. **Audit trail:** Every overridden annotation traces back to its origin, the system's recommendation, and the human decision.  
2. **Pipeline tuning:** Concepts that users frequently resurrect signal Judge prompt failures. Concepts users consistently select from Panel B (Judge recommendation) over Panel A (EntityRuler) signal EntityRuler matching improvements.  
3. **Feedback loop:** Resurrection patterns feed into confidence tier recalibration (see §13, Future Enhancement \#16).

**6.8.4.4 FOLIO Mapper Component Reuse**

The resurrection panel reuses these existing FOLIO Mapper components:

| FOLIO Mapper Component | Location | Usage in Resurrection Panel |
| ----- | ----- | ----- |
| **Tree visualization** | `packages/core/src/folio/` | Render ancestry trees for both panels; expandable/collapsible nodes |
| **Branch color coding** | `packages/core/src/folio/` | Color-code each panel's tree by FOLIO branch |
| **Detail endpoint** | `POST /api/mapping/detail` | Fetch ancestors, children, siblings for any selected concept |
| **Label search** | `POST /api/mapping/candidates` | Find all FOLIO concepts matching the EntityRuler's text |
| **Hierarchy traversal** | `backend/app/services/folio_service.py` → `get_ancestors()`, `get_children()` | Build full tree paths from leaf to root |

No new tree rendering code needed — the resurrection panel composes existing FOLIO Mapper components into a dual-panel layout.

**6.8.4.5 Resurrection API Endpoint**

POST /api/annotate/resurrect  
Body: {  
  "job\_id": "...",  
  "annotation\_id": "ann\_055",  
  "selected\_iri": "folio:EngTerms\_AccInt",  
  "selection\_source": "panel\_a\_drill\_down"  
}  
Response: {  
  "annotation\_id": "ann\_055",  
  "updated": true,  
  "new\_iri": "folio:EngTerms\_AccInt",  
  "new\_label": "Accrued Interest",  
  "new\_branch": "Engagement Terms"  
}

The endpoint updates the annotation in the persistence layer and pushes an SSE event to the frontend:

event: annotation\_resurrected  
data: {"annotation\_id": "ann\_055", "state": "confirmed",  
       "iri": "folio:EngTerms\_AccInt", "label": "Accrued Interest",  
       "user\_override": true}

#### **6.8.5 API Endpoints**

| Endpoint | Method | Purpose |
| ----- | ----- | ----- |
| `/api/annotate/upload` | POST | Upload document \+ optional metadata overrides (jurisdiction, court, etc.); returns `job_id` \+ SSE stream URL |
| `/api/annotate/stream/{job_id}` | GET | SSE stream of progressive results (includes `document_metadata` events) |
| `/api/annotate/result/{job_id}` | GET | Complete annotation \+ triple \+ metadata JSON |
| `/api/annotate/result/{job_id}?format={fmt}` | GET | Results in specified format: `json` (default), `parquet`, `elasticsearch`, `neo4j`, `rag_chunks`, `csv`, `jsonld`, `rdf`, `brat`, `html`, `xml`, `jsonl` |
| `/api/annotate/metadata/{job_id}` | GET | Document metadata only (type, parties, court, dates, concept summary) |
| `/api/annotate/triples/{job_id}` | GET | Triples only (for KG consumers) |
| `/api/annotate/resurrect` | POST | User overrides a rejected annotation; triggers targeted Judge call \+ updates persistence |
| `/api/annotate/export` | POST | Export a completed job in a specified format |
| `/api/annotate/batch-export` | POST | Merge and export annotations from multiple documents |
| `/api/annotate/generate` | POST | Generate synthetic legal document by type/length/jurisdiction; auto-submit to annotation pipeline |

The `?format=` parameter lets a legal tech company call a single endpoint and receive the exact format their downstream system needs — no intermediate JSON handling, no separate export step. `GET /api/annotate/result/{job_id}?format=parquet` returns a Parquet file directly. `?format=elasticsearch` returns NDJSON ready for `POST _bulk`.

**Large result sets:** For documents with thousands of annotations, the JSON result endpoint supports optional pagination via `?offset=0&limit=100` on the `annotations` array. When `offset` or `limit` is provided, the response includes `total_annotations` and `has_more` fields. When omitted (the default), the full annotation set is returned — suitable for API integration use cases where the consumer processes the complete result. The SSE stream (`GET /api/annotate/stream/{job_id}`) provides the incremental alternative for large documents.

**GET `?format=` vs. POST `/export`:** The `?format=` parameter on the result endpoint is a convenience method that returns the result in the specified format with default options. The `POST /api/annotate/export` endpoint supports additional format-specific options (e.g., `{"delimiter": "\t"}` for CSV, `{"include_js_tooltip": false}` for HTML, `{"merge": true}` for batch export). Use `?format=` for simple single-document retrieval; use `POST /export` for customized or batch exports.

---

### **6.9 Annotation Export System**

The annotation pipeline produces structured span annotations that downstream systems consume: document management backends, case management systems, project management tools, analytics platforms, knowledge graphs, NLP training pipelines, and compliance engines. Each ecosystem speaks a different format. The export system converts the pipeline's internal annotation representation into the format each consumer requires.

**Critical distinction:** FOLIO Mapper already exports 8 formats (`backend/app/services/export_service.py`) — but those export *taxonomy mappings* (term → FOLIO IRI). The annotation pipeline exports *span annotations* across 12 formats (8 Tier 1 \+ 4 Tier 2) — document position \+ context \+ FOLIO IRI \+ branch \+ definition. Different payload, different schema, different consumers. The annotation export service extends FOLIO Mapper's export infrastructure with annotation-aware serializers.

#### **6.9.1 Export Format Tiers**

**Tier 1 — Core formats (v1, required):**

| Format | Extension | Consumer Systems | Why This Format |
| ----- | ----- | ----- | ----- |
| **JSON** (native) | `.json` | REST APIs, JavaScript frontends, NoSQL databases (MongoDB, Elasticsearch), any modern backend | Universal interchange; pipeline's internal representation; zero conversion cost; supports full annotation fidelity including stacked multi-branch annotations |
| **W3C Web Annotation (JSON-LD)** | `.jsonld` | Annotation-aware platforms (Hypothesis, IIIF, Apache Annotator), linked data systems, semantic web | W3C Recommendation for annotation interchange; uses `TextPositionSelector` and `TextQuoteSelector`; enables cross-platform annotation portability |
| **XML (standoff)** | `.xml` | Enterprise DMS (iManage, OpenText, NetDocuments), legal XML (Akoma Ntoso), Java/.NET backends, SharePoint, GATE NLP | Enterprise legal tech still runs heavily on XML; standoff format keeps annotations separate from source text; schema-validatable via XSD |
| **CSV** | `.csv` | Analytics pipelines, SQL bulk import (`COPY INTO`), spreadsheet review, BI tools (Tableau, Power BI), data warehouses (Snowflake, BigQuery) | Flattened tabular view — one row per annotation occurrence; easiest path to SQL and spreadsheet ecosystems |
| **JSONL (JSON Lines)** | `.jsonl` | ML training pipelines (Label Studio, Prodigy, spaCy), streaming ingestion (Kafka, Kinesis, Pulsar), log aggregation (ELK stack) | One JSON object per line; streamable without buffering the full document; NLP community's standard training data format |

**Tier 2 — Integration formats (v1, for legal tech / enterprise consumers):**

| Format | Extension | Consumer Systems | Why This Format |
| ----- | ----- | ----- | ----- |
| **Parquet** | `.parquet` | Data science (Pandas, Spark, Jupyter), BI tools (Tableau, Power BI), data lakes (Databricks, BigQuery) | One row per annotation with document metadata denormalized onto every row. Legal tech companies concatenate per-document Parquet files into corpus-level analytics datasets with zero transformation. |
| **Elasticsearch bulk JSON** | `.ndjson` | Search platforms (Elasticsearch, OpenSearch), document management systems | NDJSON format with `_index` and `_id` fields — directly ingestible via `POST _bulk`. Each annotation becomes a searchable document with FOLIO IRI and branch facets. |
| **Neo4j CSV bundle** | `.zip` (3 CSVs) | Graph databases (Neo4j, Amazon Neptune), knowledge graph teams | Three CSV files: `nodes.csv` (concepts), `relationships.csv` (triples), `documents.csv` (metadata). Follow Neo4j's `neo4j-admin database import` format. Direct graph database import. |
| **RAG-ready chunk JSON** | `.json` | Vector stores (ChromaDB, Pinecone, Weaviate), RAG pipelines, LLM retrieval systems | Each Stage 3 chunk enriched with FOLIO concept IRIs, branch tags, and document metadata as filterable fields. Enables deterministic concept-filtered retrieval BEFORE (or instead of) probabilistic vector search. |
| **RDF/Turtle** | `.ttl` | Knowledge graphs (Neo4j RDF, GraphDB, Blazegraph), SPARQL endpoints, ontology tools (Protégé) | FOLIO concepts already have IRIs; Turtle serialization creates a queryable annotation graph. Includes SPO triples from dependency parsing. |
| **brat standoff** | `.ann` \+ `.txt` | NLP annotation tools (brat, INCEpTION), academic NLP research, annotation evaluation benchmarks | De facto standard in NLP research; simple tab-delimited format; compatible with BioNLP shared tasks |
| **HTML (inline annotation)** | `.html` | Browser-based review, email delivery, static hosting, stakeholder distribution | Self-contained annotated document viewable in any browser; `<span>` tags with data attributes carry annotation metadata |

**Tier 3 — Future formats (v2):**

| Format | Extension | Consumer Systems | Why This Format |
| ----- | ----- | ----- | ----- |
| **spaCy DocBin** | `.spacy` | Python NLP pipelines, custom NER training, entity linking | Binary format for spaCy's `Doc` objects with custom entity spans mapped to FOLIO |
| **UIMA CAS XMI** | `.xmi` | Apache UIMA, IBM Watson NLP, clinical NLP pipelines | XML-based; standard in enterprise NLP; carries type system definitions |
| **Protocol Buffers** | `.pb` | gRPC microservices, high-throughput backends, mobile apps | Binary; schema-enforced; 3–10x smaller than JSON; strongly typed |
| **MessagePack** | `.msgpack` | Performance-sensitive APIs, embedded systems, Redis caching | Binary JSON-compatible; faster serialization than JSON; smaller payloads |
| **Excel** | `.xlsx` | Non-technical reviewers, compliance teams, client deliverables | Formatted spreadsheet with color-coded branch columns; FOLIO Mapper already exports Excel for mappings |

#### **6.9.2 Format Specifications**

**JSON (native format):**

The internal annotation schema (§6.8.1) serves directly as the JSON export. No transformation required.

**W3C Web Annotation (JSON-LD):**

Each annotation maps to a W3C Web Annotation object with a `TextPositionSelector` (character offsets) and a `TextQuoteSelector` (exact match \+ prefix/suffix context for robust anchoring).

{  
  "@context": "http://www.w3.org/ns/anno.jsonld",  
  "id": "urn:folio-annotation:ann\_001",  
  "type": "Annotation",  
  "motivation": "classifying",  
  "creator": {  
    "type": "Software",  
    "name": "FOLIO Annotation Pipeline v5.0"  
  },  
  "created": "2026-02-21T14:30:00Z",  
  "body": {  
    "type": "SpecificResource",  
    "source": "folio:R8pNPutX0TN6DlEqkyZuxSw",  
    "purpose": "classifying",  
    "label": "Landlord",  
    "description": "A party that owns and leases real property...",  
    "folio:branch": "Actors",  
    "folio:matchType": "exact"  
  },  
  "target": {  
    "type": "SpecificResource",  
    "source": "urn:document:contract\_2026\_001",  
    "selector": \[  
      {  
        "type": "TextPositionSelector",  
        "start": 10452,  
        "end": 10460  
      },  
      {  
        "type": "TextQuoteSelector",  
        "exact": "Landlord",  
        "prefix": "obligations of the ",  
        "suffix": " under this Section"  
      }  
    \]  
  }  
}

The `TextQuoteSelector` provides **robust anchoring** — if the canonical text shifts slightly (e.g., re-processing with updated normalization), the prefix/suffix context helps relocate the annotation even when character offsets no longer match.

For multi-branch annotations at the same span, each branch produces a separate W3C Annotation object pointing to the same target selector. An `AnnotationCollection` groups all annotations for the document.

**XML (standoff):**

Standoff XML separates annotations from the source text. The annotation file references character positions in the canonical text file.

\<?xml version="1.0" encoding="UTF-8"?\>  
\<folio-annotations  
    xmlns="urn:folio:annotation:v5"  
    xmlns:folio="urn:folio:ontology"  
    document-id="contract\_2026\_001.pdf"  
    source-format="pdf"  
    canonical-text-hash="sha256:a1b2c3d4..."  
    pipeline-version="5.0.0"  
    processed-at="2026-02-21T14:30:00Z"\>

  \<annotation id="ann\_001"  
              start="10452" end="10460"  
              text="Landlord"  
              branch="Actors"  
              match-type="exact"  
              judge-verdict="kept"\>  
    \<folio-concept iri="folio:R8pNPutX0TN6DlEqkyZuxSw"  
                   label="Landlord"  
                   definition="A party that owns and leases real property..."/\>  
    \<provenance page="14"  
                section-path="Article II \> §2.3(a)"  
                element-type="paragraph"/\>  
  \</annotation\>

  \<annotation id="ann\_042"  
              start="28910" end="28923"  
              text="United States"  
              branch="Governmental Bodies"  
              match-type="fuzzy"  
              judge-verdict="kept"\>  
    \<folio-concept iri="folio:Gov\_US\_001"  
                   label="United States Government"  
                   definition="The federal government of the United States..."/\>  
    \<provenance page="31"  
                section-path="Article XIV \> §14.1"  
                element-type="paragraph"/\>  
  \</annotation\>

  \<unresolved concept-text="anti-assignment provision"  
              branches-attempted="Contractual Clause"  
              flag="no\_folio\_match"/\>  
\</folio-annotations\>

An XSD schema validates the XML structure. The `<folio-annotations>` root element carries document-level metadata. Each `<annotation>` element contains the span, the FOLIO concept, and provenance. An XSD ships with the pipeline for consumer validation.

**CSV:**

One row per annotation occurrence. Flattened structure sacrifices nesting for universal compatibility.

annotation\_id,start,end,text,iri,label,definition,branch,match\_type,judge\_verdict,page,section\_path,element\_type,document\_id,source\_format  
ann\_001,10452,10460,Landlord,folio:R8pNPutX0TN6DlEqkyZuxSw,Landlord,"A party that owns and leases real property...",Actors,exact,kept,14,"Article II \> §2.3(a)",paragraph,contract\_2026\_001.pdf,pdf  
ann\_042,28910,28923,United States,folio:Gov\_US\_001,United States Government,"The federal government of the United States...",Governmental Bodies,fuzzy,kept,31,"Article XIV \> §14.1",paragraph,contract\_2026\_001.pdf,pdf

For SQL bulk import:

COPY annotations FROM '/path/to/export.csv'  
WITH (FORMAT csv, HEADER true, DELIMITER ',');

**JSONL (JSON Lines):**

One annotation per line. Identical structure to the JSON `annotations` array, but newline-delimited for streaming.

{"id":"ann\_001","start":10452,"end":10460,"text":"Landlord","iri":"folio:R8pNPutX0TN6DlEqkyZuxSw","label":"Landlord","branch":"Actors","match\_type":"exact","judge\_verdict":"kept","provenance":{"page":14,"section\_path":"Article II \> §2.3(a)"}}  
{"id":"ann\_042","start":28910,"end":28923,"text":"United States","iri":"folio:Gov\_US\_001","label":"United States Government","branch":"Governmental Bodies","match\_type":"fuzzy","judge\_verdict":"kept","provenance":{"page":31,"section\_path":"Article XIV \> §14.1"}}

Compatible with `jq`, Kafka producers, Label Studio import, and spaCy's `srsly.read_jsonl()`.

**RDF/Turtle:**

@prefix folio: \<http://purl.org/folio/\> .  
@prefix oa: \<http://www.w3.org/ns/oa\#\> .  
@prefix ann: \<urn:folio-annotation:\> .  
@prefix doc: \<urn:document:\> .

ann:ann\_001 a oa:Annotation ;  
    oa:hasBody folio:R8pNPutX0TN6DlEqkyZuxSw ;  
    oa:hasTarget \[  
        a oa:SpecificResource ;  
        oa:hasSource doc:contract\_2026\_001 ;  
        oa:hasSelector \[  
            a oa:TextPositionSelector ;  
            oa:start 10452 ;  
            oa:end 10460  
        \]  
    \] ;  
    folio:branch "Actors" ;  
    folio:matchType "exact" .

FOLIO Mapper already exports RDF/Turtle for taxonomy mappings (`backend/app/services/export_service.py`). The annotation exporter extends this with `oa:TextPositionSelector` triples.

**brat standoff (.ann):**

T1	FOLIO\_Actors 10452 10460	Landlord  
T2	FOLIO\_GovernmentalBodies 28910 28923	United States  
\#1	AnnotatorNotes T1	IRI=folio:R8pNPutX0TN6DlEqkyZuxSw | Label=Landlord | MatchType=exact  
\#2	AnnotatorNotes T2	IRI=folio:Gov\_US\_001 | Label=United States Government | MatchType=fuzzy

Paired with the canonical text saved as `.txt`. Entity types use the pattern `FOLIO_{BranchName}` to carry branch information within brat's type system.

**HTML (inline annotation):**

\<span class="folio-annotation"  
      data-iri="folio:R8pNPutX0TN6DlEqkyZuxSw"  
      data-branch="Actors"  
      data-label="Landlord"  
      data-definition="A party that owns and leases real property..."  
      style="background-color: rgba(66, 133, 244, 0.2); cursor: pointer;"\>  
  Landlord  
\</span\>

The HTML export produces a self-contained file: the full canonical text with `<span>` tags wrapping each annotated concept. An embedded stylesheet and JavaScript tooltip handler make the file viewable in any browser without dependencies. Branch colors come from FOLIO Mapper's color palette (`packages/core/src/folio/`).

**Parquet:**

One row per annotation with document metadata denormalized onto every row. Three output files per document:

* `annotations.parquet`: one row per annotation occurrence (columns: `doc_id`, `document_type`, `court`, `case_number`, `ann_id`, `start`, `end`, `text`, `folio_iri`, `folio_label`, `branch`, `discovery_source`, `confidence_tier`, `state`, `judge_verdict`, `page`, `section_path`)  
* `triples.parquet`: one row per SPO triple (columns: `doc_id`, `subject_iri`, `subject_label`, `predicate_iri`, `predicate_lemma`, `object_iri`, `object_label`, `sentence`)  
* `metadata.parquet`: one row per document (all `document_metadata` fields flattened)

A legal tech company concatenates thousands of `annotations.parquet` files: `pd.concat([pd.read_parquet(f) for f in glob("*.parquet")])` → instant corpus analytics.

**Elasticsearch Bulk JSON:**

NDJSON format directly ingestible via `POST _bulk`:

{"index": {"\_index": "folio\_annotations", "\_id": "doc001\_ann\_001"}}  
{"document\_id": "doc001", "document\_type": "Motion to Dismiss", "court": "SDNY", "case\_number": "1:2025-cv-01234", "annotation\_id": "ann\_001", "start": 10452, "end": 10460, "text": "Landlord", "folio\_iri": "folio:R8pNPutX0TN6DlEqkyZuxSw", "folio\_label": "Landlord", "branch": "Actors", "discovery\_source": "both", "page": 14, "section\_path": "Article II \> §2.3(a)"}

Each document's export appends to the same Elasticsearch index. Concept-faceted search works immediately: `"query": {"bool": {"filter": [{"term": {"branch": "Actors"}}, {"term": {"folio_label": "Landlord"}}]}}`.

**Neo4j CSV Bundle:**

Three CSV files in a `.zip` following Neo4j's `neo4j-admin database import` format:

`nodes.csv`:

:ID,name,folio\_iri,folio\_label,branch,:LABEL  
doc001\_ann\_001,Landlord,folio:R8p...,Landlord,Actors,Concept;Actor  
doc001\_ann\_042,Motion to Dismiss,folio:DocArt\_MTD...,Motion to Dismiss,Document Artifacts,Concept;DocumentArtifact

`relationships.csv`:

:START\_ID,:END\_ID,:TYPE,sentence,document\_id  
doc001\_ann\_042,doc001\_ann\_055,TARGETS,"The motion to dismiss the breach claim...",doc001  
doc001\_ann\_060,doc001\_ann\_042,RULED\_ON,"The court denied the motion...",doc001

`documents.csv`:

:ID,filename,document\_type,court,case\_number,filing\_date,:LABEL  
doc001,Acme\_v\_Smith\_MTD.pdf,Motion to Dismiss,SDNY,1:2025-cv-01234,2025-03-15,Document

**RAG-Ready Chunk Metadata JSON:**

Each Stage 3 chunk enriched with FOLIO concept metadata for vector store ingestion:

{  
  "chunks": \[  
    {  
      "chunk\_id": "chunk\_0",  
      "text": "ARTICLE IV. DEFAULT AND REMEDIES. Section 4.1...",  
      "start\_char": 15000,  
      "end\_char": 18500,  
      "page": 8,  
      "section\_path": "Article IV \> §4.1",  
      "document\_metadata": {  
        "document\_id": "doc001",  
        "document\_type": "Commercial Lease",  
        "court": null,  
        "parties": \["Acme Corp", "John Smith"\]  
      },  
      "folio\_concepts": \[  
        {"iri": "folio:EngTerms\_Default\_001", "label": "Default", "branch": "Engagement Terms"},  
        {"iri": "folio:CC\_Termination\_001", "label": "Termination", "branch": "Contractual Clause"}  
      \],  
      "folio\_iris": \["folio:EngTerms\_Default\_001", "folio:CC\_Termination\_001"\],  
      "folio\_branches": \["Engagement Terms", "Contractual Clause"\],  
      "triples\_in\_chunk": \[  
        {"subject": "Landlord", "predicate": "may terminate", "object": "Lease"}  
      \]  
    }  
  \]  
}

The RAG system ingests each chunk into its vector store with FOLIO metadata as filterable fields. Retrieval: "Find chunks where `folio_concepts` contains 'Default' AND `document_type` \= 'Commercial Lease'" — deterministic concept filtering BEFORE (or instead of) probabilistic vector search.

#### **6.9.3 Export Architecture**

\# backend/app/services/annotation\_export\_service.py (NEW)

from enum import Enum

class AnnotationExportFormat(Enum):  
    JSON \= "json"             \# Native format  
    JSONLD \= "jsonld"         \# W3C Web Annotation  
    XML \= "xml"               \# Standoff XML  
    CSV \= "csv"               \# Tabular  
    JSONL \= "jsonl"           \# JSON Lines (streaming)  
    TURTLE \= "turtle"         \# RDF/Turtle  
    BRAT \= "brat"             \# brat standoff (.ann \+ .txt)  
    HTML \= "html"             \# Inline annotated HTML  
    PARQUET \= "parquet"       \# Columnar analytics (Tier 2\)  
    ELASTICSEARCH \= "elasticsearch"  \# Bulk NDJSON (Tier 2\)  
    NEO4J \= "neo4j"           \# CSV bundle for graph import (Tier 2\)  
    RAG\_CHUNKS \= "rag\_chunks" \# Concept-tagged chunks for RAG (Tier 2\)

\# Each format has a dedicated serializer  
SERIALIZERS \= {  
    AnnotationExportFormat.JSON: serialize\_json,  
    AnnotationExportFormat.JSONLD: serialize\_w3c\_jsonld,  
    AnnotationExportFormat.XML: serialize\_standoff\_xml,  
    AnnotationExportFormat.CSV: serialize\_csv,  
    AnnotationExportFormat.JSONL: serialize\_jsonl,  
    AnnotationExportFormat.TURTLE: serialize\_turtle,  
    AnnotationExportFormat.BRAT: serialize\_brat,
    AnnotationExportFormat.HTML: serialize\_inline\_html,
    \# Tier 2
    AnnotationExportFormat.PARQUET: serialize\_parquet,
    AnnotationExportFormat.ELASTICSEARCH: serialize\_elasticsearch\_bulk,
    AnnotationExportFormat.NEO4J: serialize\_neo4j\_csv,
    AnnotationExportFormat.RAG\_CHUNKS: serialize\_rag\_chunks,
}

async def export\_annotations(  
    annotation\_result: AnnotationResult,  
    canonical\_text: str,  
    format: AnnotationExportFormat,  
    options: dict | None \= None,  
) \-\> bytes | str:  
    """  
    Convert the internal annotation result to the requested format.  
      
    Each serializer receives the full annotation result (annotations,  
    resolution cache, statistics, unresolved) plus the canonical text.  
      
    Options dict allows format-specific customization:  
      \- csv: {"delimiter": ",", "include\_definition": true}  
      \- html: {"include\_js\_tooltip": true, "branch\_colors": true}  
      \- xml: {"include\_xsd": true}  
      \- jsonld: {"compact": true}  
      \- brat: {"entity\_type\_prefix": "FOLIO\_"}  
      
    FOLIO Mapper cross-reference:  
      \- Extends backend/app/services/export\_service.py  
      \- Reuses FOLIO Mapper's export infrastructure for file generation  
      \- Branch colors from packages/core/src/folio/  
    """  
    serializer \= SERIALIZERS\[format\]  
    return await serializer(annotation\_result, canonical\_text, options)

#### **6.9.4 Export API Endpoint**

The `/api/annotate/export` endpoint accepts a job ID and format parameter:

\# backend/app/routers/annotation\_router.py — export endpoint

@router.post("/export")  
async def export\_annotations\_endpoint(  
    job\_id: str,  
    format: AnnotationExportFormat,  
    options: dict | None \= None,  
):  
    """  
    Export annotations for a completed job.  
      
    Returns the appropriate MIME type per format:
      json          → application/json
      jsonld        → application/ld+json
      xml           → application/xml
      csv           → text/csv
      jsonl         → application/x-ndjson
      turtle        → text/turtle
      brat          → application/zip (contains .ann \+ .txt)
      html          → text/html
      parquet       → application/octet-stream
      elasticsearch → application/x-ndjson
      neo4j         → application/zip (contains nodes.csv \+ edges.csv)
      rag\_chunks    → application/json
    """  
    result \= load\_annotation\_result(job\_id)  
    canonical \= load\_canonical\_text(job\_id)  
      
    content \= await export\_annotations(result, canonical, format, options)  
      
    mime\_types \= {  
        AnnotationExportFormat.JSON: "application/json",  
        AnnotationExportFormat.JSONLD: "application/ld+json",  
        AnnotationExportFormat.XML: "application/xml",  
        AnnotationExportFormat.CSV: "text/csv",  
        AnnotationExportFormat.JSONL: "application/x-ndjson",  
        AnnotationExportFormat.TURTLE: "text/turtle",  
        AnnotationExportFormat.BRAT: "application/zip",
        AnnotationExportFormat.HTML: "text/html",
        \# Tier 2
        AnnotationExportFormat.PARQUET: "application/octet-stream",
        AnnotationExportFormat.ELASTICSEARCH: "application/x-ndjson",
        AnnotationExportFormat.NEO4J: "application/zip",
        AnnotationExportFormat.RAG\_CHUNKS: "application/json",
    }
      
    return Response(  
        content=content,  
        media\_type=mime\_types\[format\],  
        headers={"Content-Disposition": f"attachment; filename={job\_id}.{format.value}"}  
    )

#### **6.9.5 Lossless vs. Lossy Export**

Not every format carries full annotation fidelity. The export system distinguishes lossless and lossy formats:

| Format | Fidelity | What Gets Lost |
| ----- | ----- | ----- |
| **JSON** (native) | **Lossless** | Nothing — canonical internal representation |
| **JSON-LD** | **Lossless** | Nothing — W3C model accommodates all fields via FOLIO namespace extensions |
| **XML** | **Lossless** | Nothing — XSD schema carries all fields |
| **RDF/Turtle** | **Lossless** | Nothing — custom predicates carry FOLIO-specific metadata |
| **JSONL** | **Near-lossless** | Document-level metadata (statistics, resolution cache) omitted; per-annotation data intact |
| **CSV** | **Lossy** | Nested provenance flattened; definition text truncated if \>1000 chars; multi-branch stacking lost (each branch \= separate row) |
| **brat** | **Lossy** | No definitions, no hierarchy path, no match confidence; FOLIO metadata compressed into notes |
| **HTML** | **Lossy** | Optimized for human viewing; annotation metadata in data attributes, not queryable |

For round-trip workflows (export → modify externally → re-import), use JSON, JSON-LD, or XML. For one-way analytics or review, CSV, JSONL, and HTML suffice.

#### **6.9.6 Batch Export for Document Portfolios**

When processing multiple documents, the export system supports batch export:

\# POST /api/annotate/batch-export  
{  
    "job\_ids": \["job\_001", "job\_002", "job\_003"\],  
    "format": "csv",  
    "merge": true  \# Combine all documents into one CSV  
}

Merged CSV adds a `document_id` column. Merged JSONL concatenates all documents' annotations into one stream. Merged Parquet (v2) partitions by `document_id` for efficient columnar queries.

For analytics use cases ("which FOLIO concepts appear most frequently across 500 contracts?"), the merged CSV/JSONL/Parquet exports enable direct SQL or pandas aggregation without per-document file handling.

---

### **6.10 Synthetic Legal Document Generator**

#### **6.10.1 Purpose**

Users need to test the annotation pipeline without uploading real client documents — which carry confidentiality obligations, privilege concerns, and data governance restrictions. The synthetic document generator lets users select a document type from a categorized menu and receive a realistic synthetic legal document that exercises the pipeline's full capability.

The generated document feeds directly into the annotation pipeline as if the user had uploaded a real file. The pipeline processes it identically — ingestion, canonical text assembly, EntityRuler, LLM concept identification, reconciliation, resolution, string matching, dependency parsing, metadata extraction, and export.

#### **6.10.2 Document Type Selection UI**

The UI displays primary categories as top-level items. Each category expands into specific document subtypes via a collapsible tree:

┌─────────────────────────────────────────────────────┐  
│  Generate Synthetic Legal Document                   │  
│                                                      │  
│  Select a document type:                             │  
│                                                      │  
│  ▸ Litigation                                        │  
│  ▸ Contracts                                         │  
│  ▸ Corporate / Governance                            │  
│  ▸ Regulatory / Compliance                           │  
│  ▸ Law Firm Operations                               │  
│  ▸ Real Estate                                       │  
│  ▸ Intellectual Property                             │  
│  ▸ Estate Planning / Probate                         │  
│  ▸ Immigration                                       │  
│                                                      │  
│  Length:  ○ Short (1–5 pages)                        │  
│          ● Medium (10–30 pages)                      │  
│          ○ Long (50–100 pages)                       │  
│                                                      │  
│  Jurisdiction (optional): \[  New York  ▾\]            │  
│                                                      │  
│        \[ Generate & Annotate \]                       │  
└─────────────────────────────────────────────────────┘

Expanding a category reveals its subtypes:

 ▾ Litigation  
      Complaint  
      Motion to Dismiss  
      Motion for Summary Judgment  
      Answer / Responsive Pleading  
      Court Opinion / Order  
      Discovery Requests  
      Discovery Responses  
      Deposition Transcript  
      Subpoena  
      Stipulation  
      Settlement Agreement

  ▾ Contracts  
      Commercial Lease  
      Residential Lease  
      Employment Agreement  
      Non-Disclosure Agreement (NDA)  
      Asset Purchase Agreement  
      Merger Agreement  
      Stock Purchase Agreement  
      Loan Agreement  
      Promissory Note  
      License Agreement (IP / Software)  
      Services Agreement / MSA  
      Partnership Agreement / Operating Agreement  
      Letter of Intent

  ▾ Corporate / Governance  
      Board Resolution  
      Bylaws  
      Articles of Incorporation  
      Shareholder Agreement  
      Proxy Statement  
      Annual Report Excerpt (10-K)

  ▾ Regulatory / Compliance  
      Regulatory Filing  
      Compliance Policy  
      Privacy Policy  
      Terms of Service

  ▾ Law Firm Operations  
      Time Entry Narrative  
      Legal Memorandum (Research Memo)  
      Demand Letter  
      Cease and Desist Letter  
      Client Engagement Letter  
      Legal Opinion Letter

  ▾ Real Estate  
      Purchase and Sale Agreement  
      Deed  
      Title Report Excerpt  
      Easement Agreement

  ▾ Intellectual Property  
      Patent Claim  
      Trademark Application Excerpt  
      IP Assignment Agreement

  ▾ Estate Planning / Probate  
      Last Will and Testament  
      Trust Agreement  
      Power of Attorney

  ▾ Immigration  
      Visa Petition Supporting Letter  
      Asylum Declaration

If the user clicks a primary category without expanding it, the LLM generates a representative document of that category (e.g., clicking "Litigation" generates a Complaint as the default litigation document type). Clicking a specific subtype generates that exact document type.

#### **6.10.3 Generation Parameters**

| Parameter | Options | Default | Purpose |
| ----- | ----- | ----- | ----- |
| **Document type** | Any category or subtype from the tree | Required selection | Determines the document's structure, vocabulary, and FOLIO concept density |
| **Length** | Short (1–5 pages), Medium (10–30 pages), Long (50–100 pages) | Medium | Controls document size; exercises different pipeline performance characteristics |
| **Jurisdiction** | Optional dropdown: US federal, any US state, England & Wales, Canada, Australia, or "Generic" | Generic | Adjusts statutory references, court names, citation formats, and jurisdiction-specific terminology |

#### **6.10.4 Generation Strategy**

The LLM generates synthetic documents using a structured prompt that ensures:

1. **Realistic structure.** A Motion to Dismiss follows the structure of a real motion: caption, introduction, factual background, legal standard, argument sections, conclusion, signature block. A commercial lease includes recitals, defined terms, premises description, rent provisions, default provisions, boilerplate.

2. **FOLIO concept density.** The prompt instructs the LLM to use legal terminology naturally — not to stuff keywords, but to write as a real attorney would. Different document types have different natural concept densities: contracts are concept-dense (every clause contains FOLIO terms); time entries are concept-sparse but practice-area-diverse.

3. **Synthetic parties, courts, and facts.** All names, case numbers, addresses, and dollar amounts are fictional. The generator never produces text that could be confused with a real case or real parties. Party names use obviously synthetic names or a disclaimer watermark.

4. **Jurisdiction-appropriate references.** If the user selects "New York," the complaint references CPLR provisions, files in the Supreme Court of the State of New York, and cites New York case law patterns. If "Federal," the motion references the Federal Rules of Civil Procedure and files in a U.S. District Court.

5. **Length calibration.** Short documents omit optional sections. Medium documents include all standard sections. Long documents add exhibits, schedules, detailed recitals, and extended boilerplate.

**Generation prompt structure:**

SYSTEM:  
You generate realistic synthetic legal documents for testing a legal  
annotation pipeline. The document must read as if drafted by a  
practicing attorney — proper structure, natural legal terminology,  
correct formatting conventions. All parties, case numbers, addresses,  
and facts are fictional.

USER:  
DOCUMENT TYPE: {selected\_type} (FOLIO: {folio\_document\_type\_iri})  
CATEGORY: {category}  
LENGTH: {short | medium | long}  
JURISDICTION: {jurisdiction or "Generic"}

Generate a realistic {selected\_type} with:  
\- Proper document structure (caption, sections, signature block)  
\- Natural legal terminology (do not artificially inflate legal jargon)  
\- Fictional but realistic parties, facts, and dollar amounts  
\- {jurisdiction}-appropriate statutory references and court names  
\- Length target: {page\_range} pages of text

IMPORTANT: This document will be processed by a FOLIO legal concept  
annotation pipeline. Write naturally — the pipeline should discover  
concepts organically, not from artificial keyword stuffing.

#### **6.10.5 Token Economics**

| Length | Estimated Output Tokens | Estimated Cost (Claude Sonnet) | Generation Time |
| ----- | ----- | ----- | ----- |
| Short (1–5 pages) | \~2,000–5,000 | \~$0.02–$0.08 | 5–15 seconds |
| Medium (10–30 pages) | \~10,000–30,000 | \~$0.15–$0.45 | 20–60 seconds |
| Long (50–100 pages) | \~50,000–100,000 | \~$0.75–$1.50 | 2–5 minutes |

For long documents, the generator may need multiple LLM calls (generating section by section) to stay within context window limits. Each section appends to the growing document, maintaining narrative and party consistency.

#### **6.10.6 Integration with Pipeline**

The generated document enters the pipeline at Stage 1 (Ingestion) as plain text — no file format conversion needed. The workflow:

1. User selects document type, length, jurisdiction  
2. LLM generates synthetic document text  
3. Text feeds directly into Stage 2 (Canonical Text Assembly)  
4. Pipeline processes normally — all stages execute identically to a real document  
5. User sees progressive annotations appear on the synthetic text  
6. User can export in any of the 12 supported formats

The synthetic document is also available for download as a `.txt` or `.docx` file, so users can inspect the generated text independently of the annotation results.

#### **6.10.7 API Endpoint**

POST /api/annotate/generate  
Body: {  
  "document\_type": "motion\_to\_dismiss",  
  "category": "litigation",  
  "length": "medium",  
  "jurisdiction": "new\_york\_federal"  
}  
Response: {  
  "job\_id": "gen\_001",  
  "stream\_url": "/api/annotate/stream/gen\_001",  
  "status": "generating"  
}

The endpoint generates the synthetic document, then automatically submits it to the annotation pipeline. The SSE stream first emits a `synthetic_document` event with the generated text, followed by the standard annotation events (`preliminary_annotations`, `chunk_reconciled`, etc.).

event: synthetic\_document  
data: {"text": "UNITED STATES DISTRICT COURT\\nSOUTHERN DISTRICT OF NEW YORK\\n\\nACME CORPORATION,\\n    Plaintiff,\\n\\nv.\\n\\nJOHN SMITH,...", "document\_type": "Motion to Dismiss", "length": "medium", "jurisdiction": "New York Federal", "generation\_tokens": 15000}

event: document\_text  
data: {"text": "...", "text\_range": \[0, 45000\]}

event: document\_metadata  
data: {"phase": 1, "document\_type": {"folio\_label": "Motion to Dismiss", ...}, ...}

event: preliminary\_annotations  
data: {"source": "entity\_ruler", "annotations": \[...\]}

... (standard pipeline events follow)

---

## **7\. Data Flow Summary**

                   ┌──────────────────────────────┐  
                    │  Document / Pasted Text       │  
                    │  (PDF, DOCX, MD, HTML, TXT,   │  
                    │   RTF, EML, MSG, or paste)     │  
                    └──────────────┬───────────────┘  
                                   │  
                    ┌──────────────▼───────────────┐  
                    │  Format Router                 │  
                    │  (detect format → dispatch)    │  
                    └──────────────┬───────────────┘  
                                   │  
              ┌────────────────────┼────────────────────┐  
              │                    │                     │  
         ┌────▼────┐        ┌─────▼─────┐        ┌─────▼─────┐  
         │ Docling  │        │python-docx│        │ BS4 / md  │  ...  
         │ (PDF)    │        │ (Word)    │        │(HTML/MD)  │  
         └────┬────┘        └─────┬─────┘        └─────┬─────┘  
              │                    │                     │  
              └────────────────────┼────────────────────┘  
                                   │  
                    ┌──────────────▼───────────────┐  
                    │  list\[TextElement\]             │  
                    │  (uniform intermediate format) │  
                    └──────────────┬───────────────┘  
                                   │  
           ┌───────────────────────▼──────────────────┐  
           │  Format-Aware Normalization                │  
           │  → PDF/RTF: aggressive (soft-wrap repair)  │  
           │  → HTML: moderate (whitespace collapse)    │  
           │  → Word/TXT/email: light (\\r\\n only)      │  
           │  → MD/paste: minimal                       │  
           └───────────────────────┬──────────────────┘  
                                   │  
           ┌───────────────────────▼──────────────────┐  
           │  Canonical Text Assembly \+ Freeze          │  
           │  → immutable string \+ offset map           │  
           │  → SHA-256 hash                            │  
           └───────────────────────┬──────────────────┘  
                                   │  
           ┌───────────────────────▼──────────────────┐  
           │  Chunking (zero overlap)                   │  
           └───────────────────────┬──────────────────┘  
                                   │  
              ┌────────────────────▼────────────┐  
              │  For EACH chunk:                 │  
              │  LLM → concept text              │  
              │        \+ branch name             │  
              └────────────────────┬────────────┘  
                                   │  
           ┌───────────────────────▼──────────────────┐  
           │  Deduplicate across all chunks             │  
           │  → flatten multi-branch into               │  
           │    unique (text, branch) pairs              │  
           └───────────────────────┬──────────────────┘  
                                   │  
           ┌───────────────────────▼──────────────────┐  
           │  Resolve ONCE per unique concept           │  
           │  via FOLIO Mapper's candidate search       │  
           │  → build resolution cache                  │  
           └───────────────────────┬──────────────────┘  
                                   │  
           ┌───────────────────────▼──────────────────┐  
           │  Aho-Corasick single-pass scan             │  
           │  → find every occurrence of every concept  │  
           │  → word-boundary validation per match      │  
           │  → stamp cached resolution                 │  
           │  → compute global offsets                  │  
           └───────────────────────┬──────────────────┘  
                                   │  
           ┌───────────────────────▼──────────────────┐  
           │  Judge LLM (multi-branch concepts only)    │  
           │  → extract context window per occurrence   │  
           │  → Judge keeps or rejects each branch      │  
           │  → single-branch concepts pass through     │  
           └───────────────────────┬──────────────────┘  
                                   │  
           ┌───────────────────────▼──────────────────┐  
           │  JSON Annotation Layer                     │  
           └───────────────────────┬──────────────────┘  
                                   │  
              ┌────────────────────┼────────────────────┐  
              │                    │                     │  
    ┌─────────▼────────┐  ┌──────▼──────┐   ┌─────────▼─────────┐  
    │ Frontend:         │  │  Export to   │   │  Export to        │  
    │ Clickable Spans   │  │  JSON/       │   │  CSV / JSONL /    │  
    │                   │  │  JSON-LD /   │   │  brat / HTML /    │  
    │                   │  │  XML / RDF   │   │  Parquet (v2)     │  
    └──────────────────┘  └─────────────┘   └───────────────────┘  
                            (lossless)         (lossy / streaming)

---

## **8\. The Resolve-Once Optimization in Detail**

### **8.1 Cost Savings**

For a 90-page commercial lease:

| Metric | Without Caching | With Resolve-Once |
| ----- | ----- | ----- |
| LLM-identified concept mentions across chunks | \~500 | \~500 |
| Unique (concept, branch) pairs after flattening | — | \~60 (avg 1.5 branches per concept × \~40 unique concepts) |
| FOLIO Mapper resolution calls | \~500 | \~60 |
| Resolution calls that find no match (false-positive branches) | — | \~15 (discarded silently) |
| **Net resolution calls producing annotations** | — | **\~45** |
| **Total reduction** | — | **88%** |

The multi-branch strategy adds \~50% more resolution calls compared to single-branch (\~60 vs \~40). But each call costs microseconds — a local `folio-python` search. The cost of those extra calls is negligible compared to the annotations recovered from concepts that genuinely belong in multiple branches.

**Scale projections for longer documents:**

| Document | Pages | Chars | Chunks | Unique Concepts | Concept-Branch Pairs | Occurrences Found | Stage 6 Time (Aho-Corasick) |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| Standard lease | 30 | \~150K | \~15 | \~40 | \~60 | \~500 | \~5ms |
| Complex M\&A agreement | 100 | \~500K | \~47 | \~80 | \~120 | \~2,000 | \~12ms |
| Regulatory filing \+ exhibits | 250 | \~1.2M | \~120 | \~150 | \~225 | \~5,000 | \~20ms |
| Litigation brief \+ appendices | 500 | \~2.5M | \~250 | \~200 | \~300 | \~10,000 | \~30ms |
| Multi-contract portfolio (batch) | 1,000+ | \~5M+ | \~500+ | \~300+ | \~450+ | \~25,000+ | \~60ms |

For documents beyond 500 pages, the LLM chunking and resolution stages dominate total processing time (minutes), not the string matching stage (milliseconds). Aho-Corasick ensures Stage 6 never becomes the bottleneck.

### **8.2 Consistency Guarantee**

Without caching, the same concept text could theoretically resolve to different FOLIO IRIs on different calls (e.g., if fuzzy matching produces inconsistent rankings). Resolve-once guarantees that "Landlord" maps to the same IRI in every occurrence throughout the document.

### **8.3 Cross-Chunk Discovery**

The LLM might identify "force majeure" in chunk 32 but miss it in chunks 8 and 44 (where it also appears). Because the Aho-Corasick full-document scan runs after resolution, all three occurrences get annotated — even though the LLM only spotted one.

This means the LLM functions as a **concept discoverer**, not a **per-occurrence tagger**. It needs to find each concept at least once, anywhere in the document. The deterministic layer handles exhaustive location.

For a 500-page regulatory filing with 250 chunks, the LLM processes each chunk independently and might identify "force majeure" in only 3 of 250 chunks. The Aho-Corasick scanner then finds all 15 occurrences across the full 2.5M-character text in a single \~30ms pass. The provenance lookup uses binary search (`bisect_right`) over the offset map — O(log n) per match instead of O(n) — critical when the offset map contains 5,000+ entries for a 500-page document.

---

## **9\. Edge Cases**

### **9.1 Multi-Word Concepts at Chunk Boundaries**

A concept like "breach of fiduciary duty" might straddle two chunks at a sentence-level split.

**Mitigation A (primary):** Chunk at paragraph/section boundaries. Legal drafters rarely split a concept across structural boundaries.

**Mitigation B (fallback):** The full-document string scan in Stage 6 catches these regardless — it searches the entire canonical text, not individual chunks.

### **9.2 Overlapping and Nested Concepts**

Legal language frequently nests concepts within larger concepts. The pipeline identifies and annotates both independently:

| Phrase | Outer Concept | Inner Concept(s) | Overlap Type |
| ----- | ----- | ----- | ----- |
| "Breach of Contract" | Breach of Contract (Litigation Claim) | Contract (Document Artifact) | Nested |
| "Contract Law" | Contract Law (Area of Law) | Contract (Document Artifact), Law (Legal Authority) | Nested |
| "Real Property" | Real Property (Asset Type) | Property (Asset Type) | Nested |
| "Governing Law" | Governing Law (Contractual Clause) | Law (Legal Authority) | Nested |
| "Independent Contractor" | Independent Contractor (Actor) | Contractor (Actor) | Nested |

The pipeline handles these correctly through three mechanisms: the LLM prompt (Rule 5\) explicitly requests both container and contained concepts; the Aho-Corasick scanner (§6.6.3) finds all matches in a single pass with word-boundary validation distinguishing nested concepts from substring collisions; and the flat annotation array naturally accommodates overlapping `[start, end]` ranges without hierarchical nesting in the data model.

### **9.3 Substring Collisions (False Overlaps)**

"Contract" appears inside "Subcontractor" and "Co-Landlord" contains "Landlord." These are morphological fragments, not nested concepts.

**Mitigation:** The Aho-Corasick matcher's character-class boundary validation (§6.6.6) rejects these matches. The boundary scanner treats hyphens as word characters, so "Co-Landlord" is one word — "Landlord" cannot start mid-word. "Subcontractor" is one word — "Contract" cannot start mid-word. The regex fallback (§6.6.5) uses equivalent negative lookbehind/lookahead logic.

### **9.4 Case Variations**

A document might use "LANDLORD" in headings, "Landlord" in body text, and "landlord" in lowercase. Case-insensitive matching catches all three. The resolution cache keys on `text.lower()`, so all variations resolve to the same FOLIO concept.

### **9.5 Hyphenated Legal Terms**

Intentional hyphens ("non-compete," "cross-default," "anti-dilution") survive the Stage 1 normalization because the joined form ("noncompete") doesn't exist in the dictionary or FOLIO label set. The LLM identifies "non-compete" as a concept; string matching finds all occurrences preserving the hyphen.

### **9.6 LLM Misses a Concept Entirely**

If the LLM fails to identify "estoppel" in any chunk, the LLM path alone would miss it — the concept never enters the LLM's output, and without the EntityRuler, the string scan would never search for it.

**Primary mitigation (v5.0): EntityRuler parallel path.** The EntityRuler scans the full canonical text against all 18,000+ FOLIO labels independently from the LLM. If "estoppel" appears literally in the document, the EntityRuler catches it regardless of whether the LLM identified it. The Reconciliation Layer (§6.4A) handles the merge — the EntityRuler match enters as Category D (EntityRuler only, LLM had opportunity) or Category E (no LLM coverage). The Reconciliation Judge confirms or rejects based on surrounding context.

**Secondary mitigation:** Run the LLM at a temperature that favors recall over precision. Accept more false positives (which get caught by `folio-python` resolution failure) to reduce false negatives (missed concepts).

**Remaining gap:** Contextual concepts that don't match any FOLIO label literally — e.g., "the agreement" meaning Contract — can only be discovered by the LLM. If the LLM misses a contextual concept, the EntityRuler cannot compensate. The LLM-recall temperature strategy addresses this partially.

### **9.7 Tables and Lists**

Every extractor handles tables and lists natively for its format. PDF tables come from Docling's structural detection. Word tables come from python-docx's `doc.tables` iterator. HTML tables come from BeautifulSoup's `<table>` parsing. Markdown lists come from markdown-it's token stream. Each extractor emits `TextElement` objects with `element_type="table_cell"` or `element_type="list_item"`. The canonical text assembler and downstream stages process them identically regardless of source format.

### **9.8 Empty or Trivial Documents**

| Scenario | Detection Point | Behavior |
| ----- | ----- | ----- |
| **No text extracted** (image-only PDF, corrupt file) | Stage 1: all extractors return empty `TextElement` list | Job completes with `status: "completed"`, zero annotations, and a `warning: "no_text_extracted"` field. Pipeline does not fail. |
| **Trivial text** (single word, a few characters) | Stage 2: canonical text \< 10 characters | Pipeline runs normally but skips chunking (entire text fits in one chunk). EntityRuler may find matches; LLM processes the full text as a single chunk. |
| **No legal concepts found** (recipe, technical manual) | Stage 7: zero annotations after full pipeline | Job completes successfully with zero annotations. The `statistics` object shows `total_occurrences_annotated: 0`. No error — the document simply contains no recognized FOLIO concepts. |
| **OCR garbage** (scanned document with poor recognition) | Stage 1: Docling OCR produces text; normalization detects high ratio of non-alphabetic characters | Pipeline processes normally. LLM may identify few or no concepts. The spot-check report flags unusual character distributions. Annotation count will be low. |
| **Non-English document** | Stage 4: LLM returns few concepts; EntityRuler matches English FOLIO labels only | Pipeline completes with reduced recall. Future enhancement: multi-language support (§13). |

---

## **10\. Technology Stack**

| Component | Technology | Rationale |
| ----- | ----- | ----- |
| **Existing resolution engine** | [FOLIO Mapper](https://github.com/damienriehl/folio-mapper) (`backend/app/services/folio_service.py`) | Fuzzy search, synonym expansion, branch filtering, hierarchy traversal, confidence scoring — already built and tested (155 pytest cases) |
| **Ingestion router** | Custom Python (`backend/app/services/ingestion/router.py`) | Format detection via extension \+ MIME sniffing; dispatch to format-specific extractors |
| **PDF extraction** | Docling (IBM) | Best structural extraction for legal PDFs; sections, paragraphs, tables, headers; preserves page/element metadata |
| **Word extraction** | python-docx (`.docx`); antiword or LibreOffice CLI (`.doc`) | python-docx preserves paragraph styles, heading levels, and table structure. Legacy `.doc` needs binary conversion. |
| **Markdown extraction** | markdown-it-py | Fast, spec-compliant CommonMark parser; token-based output maps cleanly to TextElement |
| **HTML extraction** | BeautifulSoup 4 | Robust tag parsing; handles malformed HTML common in court-opinion scrapes |
| **RTF extraction** | striprtf2 | Lightweight RTF-to-text conversion; handles control words without a full RTF engine |
| **Email extraction** | Python `email` (`.eml`); msg-parser (`.msg`) | Standard library handles MIME multipart; msg-parser covers Outlook's proprietary format |
| **MIME detection** | python-magic | File-type sniffing when extension is missing or ambiguous |
| **Line-break normalization** | Custom Python (NLTK word corpus \+ FOLIO label set) | No existing tool handles legal-specific dehyphenation \+ soft-wrap detection; calibrated per source format |
| **Chunking** | Custom Python \+ LangChain `RecursiveCharacterTextSplitter` (fallback) | Structural chunking primary; token-limit splitting secondary |
| **Multi-pattern matching** | `pyahocorasick` (C-backed Aho-Corasick automaton) | Single-pass scan for all concepts simultaneously; O(n \+ z) regardless of pattern count; 30–50x faster than per-concept regex for 100+ page documents |
| **Word-boundary validation** | Custom Python character-class scanner | O(n) single pass; treats hyphens as word characters to reject hyphenated-compound collisions; no external library needed |
| **String matching fallback** | Python `re` (stdlib) | Per-concept regex with hyphen-aware lookbehind/lookahead; used only when `pyahocorasick` is unavailable |
| **LLM providers** | FOLIO Mapper's LLM abstraction (`backend/app/services/llm/`) | 9 providers already integrated: OpenAI, Anthropic, Gemini, Mistral, Cohere, Llama, Ollama, LM Studio, Custom |
| **LLM judge validation** | FOLIO Mapper's Stage 3 pipeline (`backend/app/services/pipeline/`) | Optional quality pass for ambiguous resolutions |
| **Concept resolution** | FOLIO Mapper's candidate search (`POST /api/mapping/candidates`) | Fuzzy label \+ synonym matching via rapidfuzz; branch-scoped; confidence scoring |
| **Concept detail** | FOLIO Mapper's detail endpoint (`POST /api/mapping/detail`) | Full hierarchy path, children, siblings, translations (10 languages) |
| **FOLIO ontology access** | `folio-python` v0.2.0+ (loaded via FOLIO Mapper's singleton) | Official FOLIO Python library; cached locally at `~/.folio/cache` |
| **Annotation storage** | JSON files (v1) → database (v2) | JSON portable, inspectable; database enables analytics at scale |
| **Sentence boundary detection** | NuPunkt-RS (Rust binary \+ Python binding) | Legal-domain trained; 91.1% precision on legal text (vs. \~82.5% for standard spaCy); \~30M chars/sec; preserves citation integrity for "123 F.2d 456 (7th Cir. 2010)" |
| **EntityRuler** | spaCy `EntityRuler` \+ `spacy.blank("en")` | Deterministic scan of 18K FOLIO labels against canonical text; \~2–3 sec for 500 pages; runs in parallel with LLM pipeline |
| **Semantic EntityRuler** | spaCy noun chunker \+ EmbeddingService \+ FAISS | Synonym/paraphrase discovery via embedding similarity against FOLIO label index; \~6–13 sec (CPU) for 500 pages; runs as Path A extension after literal EntityRuler |
| **Embedding service (local, default)** | `sentence-transformers` (`all-mpnet-base-v2`, 768d) | Local embedding model — no internet, no API key, $0.00. \~4K sentences/sec on CPU. Pre-computes 18K FOLIO label embeddings at startup (\~5 sec). Shared singleton used by Semantic EntityRuler, Reconciliation triage, Resolution fallback, Branch Judge triage. |
| **Embedding service (cloud, optional)** | Voyage AI `voyage-law-2`, OpenAI `text-embedding-3-*`, Cohere `embed-english-v3.0` | Higher legal-domain accuracy. Provider-abstraction follows FOLIO Mapper's LLM pattern. Automatic fallback to local if cloud unreachable. Annual cost \<$2 for weekly FOLIO re-embedding. |
| **FAISS index** | `faiss-cpu` (or `faiss-gpu`) | Fast nearest-neighbor search across 18K FOLIO label embeddings. Inner product search on normalized vectors \= cosine similarity. O(n) brute-force at 18K scale is \<1ms per query. |
| **Embedding cache** | NumPy `.npz` files at `~/.folio/cache/` | Pre-computed FOLIO embeddings cached to disk. Cache key: `{model_name}_{owl_hash}`. Load from cache \<1 sec (\~28MB). Rebuild on OWL file change (\~5–30 sec). Multiple model caches coexist. |
| **Document metadata extraction** | Custom Python (`metadata_extractor.py`) \+ Metadata Judge (LLM) | Three-phase extraction: Phase 1 (document type classification from opening text), Phase 2 (structured fields from targeted sections), Phase 3 (annotation promotion from structural position). FOLIO-aligned metadata vocabulary. |
| **Parquet export** | `pyarrow` | Columnar format for analytics. Denormalized annotation rows with document metadata. Legal tech companies concatenate per-document files into corpus datasets. |
| **Reconciliation** | Custom Python (`reconciliation_service.py`) | Categorizes dual-path results (A–E); embedding triage auto-resolves obvious cases; routes ambiguous conflicts to Judge; merges into unified concept list |
| **Dependency parsing** | spaCy `en_core_web_trf` (or `en_core_web_sm` for speed) | Syntactic relation extraction for SPO triples; deterministic; \~25 sent/sec (trf) or \~200 sent/sec (sm) |
| **Interval tree** | `intervaltree` | O(log n) annotation lookup by character position; used by dependency parser to match spaCy tokens to FOLIO annotations |
| **Common word filter** | NLTK `words` corpus or custom frequency list | Separates high-confidence EntityRuler matches (legal-specific) from low-confidence (common English) for progressive rendering |
| **Streaming delivery** | Server-Sent Events (SSE) via `sse-starlette` or FastAPI `StreamingResponse` | Progressive frontend updates; one-directional server→client; works over HTTP without WebSocket complexity |
| **Annotation \+ triple export** | `backend/app/services/annotation_export_service.py` (new) | 8 annotation-aware formats: JSON, W3C JSON-LD, XML standoff, CSV, JSONL, RDF/Turtle, brat standoff, HTML. Triples included in JSON, JSON-LD, and RDF/Turtle exports. Distinct from FOLIO Mapper's mapping export — carries span positions, context, provenance, and KG triples |
| **Mapping export** | FOLIO Mapper's export service (`backend/app/services/export_service.py`) | 8 mapping formats (CSV, Excel, JSON, RDF/Turtle, JSON-LD, Markdown, HTML, PDF) — reused for resolution cache export |
| **W3C Web Annotation** | `pyld` (JSON-LD processing) | W3C Recommendation compliance; `TextPositionSelector` and `TextQuoteSelector` support |
| **XML serialization** | `lxml` (already a dependency for HTML extraction) | Fast XML generation; XSD validation for standoff export |
| **Frontend** | FOLIO Mapper's React app (`apps/web/`) \+ new annotation components | Reuses existing Zustand stores, Tailwind styling, component library (35 components) |

---

## **11\. Acceptance Criteria**

### **11.1 Functional**

| ID | Criterion | Validation |
| ----- | ----- | ----- |
| F1 | Pipeline processes a 100-page commercial lease (PDF) end-to-end without error | Integration test |
| F1a | Pipeline processes a 50-page Word document (.docx) end-to-end without error | Integration test |
| F1b | Pipeline processes Markdown, HTML, RTF, plain text, and email inputs without error | Integration test per format |
| F1c | Pipeline processes pasted text (no file upload) without error | Integration test |
| F2 | Every annotation's `text` field exactly equals `canonical_text[start:end]` | Automated assertion |
| F3 | Every resolved annotation maps to a valid FOLIO IRI retrievable via `folio-python` | Automated IRI check |
| F4 | Each unique concept resolves against FOLIO Mapper exactly once (cache hit on subsequent occurrences) | Assert resolution-call count equals unique-concept count |
| F5 | PDF soft-wrapped lines ("breach of\\ncontract") normalize to continuous text | Unit tests with known-broken PDFs |
| F6 | PDF hyphenated splits ("indemni-\\nfication") rejoin when joined form exists in dictionary/FOLIO | Unit tests |
| F7 | Intentional hyphens ("non-compete") survive normalization intact across all formats | Unit tests |
| F8 | Full-document string scan finds occurrences the LLM missed in specific chunks | Test: inject known concept in chunk where LLM output omits it; verify annotation appears |
| F9 | Clicking an annotated span displays the correct FOLIO definition | Manual QA |
| F10 | Unresolved concepts appear in `unresolved` array with context | Inspect JSON output |
| F11 | Format router correctly detects and dispatches all supported formats | Unit test: submit each format, verify correct extractor activates |
| F12 | Word extractor preserves heading hierarchy and table structure | Unit test: compare extracted TextElements against known Word document structure |
| F13 | HTML extractor strips scripts, styles, and navigation while preserving semantic content | Unit test: compare against hand-verified extraction |
| F14 | Email extractor strips signatures and legal disclaimers | Unit test with sample .eml containing boilerplate |
| F15 | Markdown extractor preserves code blocks verbatim (no concept annotation inside code) | Unit test: verify code\_block elements excluded from LLM annotation |
| F16 | Judge fires only for multi-branch concepts; single-branch concepts bypass Judge entirely | Assert: Judge LLM call count \= count of concepts with 2+ resolved branches |
| F17 | Judge receives surrounding sentence context for each occurrence, not just the concept text | Inspect Judge prompt logs; verify context window includes ≥1 complete sentence |
| F18 | Judge-rejected annotations carry `judge_verdict: "rejected"` and `judge_reason` in output | Inspect JSON output for rejected annotations |
| F19 | When Judge is unavailable, all annotations pass through unfiltered (graceful degradation) | Integration test: disable LLM; verify all multi-branch annotations survive |
| F20 | JSON export round-trips losslessly: export → re-import → compare yields identical annotation set | Automated: export, re-import, deep-compare |
| F21 | W3C JSON-LD export validates against the W3C Web Annotation Data Model schema | Automated: validate each exported annotation against `http://www.w3.org/ns/anno.jsonld` context |
| F22 | XML standoff export validates against the pipeline's XSD schema | Automated: `lxml` XSD validation on export output |
| F23 | CSV export produces one row per annotation with correct column values | Unit test: export known annotation set, verify row count and field values |
| F24 | JSONL export streams line-by-line without loading full document into memory | Integration test: export 10,000-annotation document; verify constant memory usage |
| F25 | brat export produces valid `.ann` \+ `.txt` file pair importable by brat/INCEpTION | Manual test: import into brat, verify annotations display correctly |
| F26 | HTML export produces a self-contained file viewable in any browser without dependencies | Manual test: open in Chrome, Firefox, Safari; verify tooltip displays FOLIO metadata on click |
| F27 | Batch export (merged CSV) combines annotations from multiple documents with correct `document_id` column | Automated: batch-export 3 jobs, verify all annotations present with correct document attribution |
| F28 | Nested concepts produce overlapping annotations: "Breach of Contract" and "Contract" both annotated at correct overlapping ranges | Unit test: input text containing "Breach of Contract"; verify two annotations with overlapping `[start, end]` ranges |
| F29 | Substring collisions rejected: "Contract" does NOT match inside "Subcontractor"; "Landlord" does NOT match inside "Co-Landlord" | Unit test: input text containing "Subcontractor" and "Co-Landlord"; verify no spurious annotations |
| F30 | Frontend displays both annotations when user clicks on "Contract" within "Breach of Contract" | Manual QA: click on the inner concept; verify tooltip shows both the inner and outer concept annotations |
| F31 | EntityRuler identifies all literal FOLIO labels in document | Unit test: seed document with 20 known FOLIO labels; verify EntityRuler finds all 20 |
| F32 | EntityRuler high-confidence matches appear within 3 seconds of upload | Performance test: upload 100-page document; measure time to first `preliminary_annotations` SSE event |
| F33 | EntityRuler low-confidence matches (common English words) render with distinct visual uncertainty indicators (dotted border, "?" badge, or reduced opacity), visually differentiated from high-confidence matches | Unit test: verify "Interest," "Term," "Party" appear as preliminary annotations with `confidence_tier: "low"` and distinct visual treatment from high-confidence matches |
| F34 | Reconciliation Category A (both agree) produces `discovery_source: "both"` with LLM's branch classification | Automated: verify merged concept list for concepts found by both paths |
| F35 | Reconciliation Category D (EntityRuler only, LLM skipped) triggers Judge, which correctly keeps legal usage ("pay Interest at 5%") and rejects non-legal usage ("no interest in attending") | Unit test with both contexts; verify Judge verdicts |
| F36 | NuPunkt-RS preserves citation integrity: "See Smith v. Jones, 123 F.2d 456 (7th Cir. 2010)." remains one sentence | Unit test against legal citation test suite |
| F37 | Dependency parser extracts correct SPO triple from "The court denied the motion" → (court, denied, motion) with FOLIO IRIs | Unit test: verify triple structure and IRI assignments |
| F38 | Dependency parser fires only on sentences with 2+ FOLIO concepts including at least one FOLIO verb | Assert: zero triples from sentences with only noun concepts |
| F39 | SSE stream delivers events in correct order: `document_text` → `preliminary_annotations` → `chunk_reconciled` → `pipeline_complete` | Integration test: record SSE event sequence; verify ordering |
| F40 | Progressive rendering: preliminary annotations upgrade to "confirmed" without visual flicker when LLM results arrive | Manual QA: observe annotation transitions during pipeline execution |
| F41 | RDF/Turtle export includes both span annotations and SPO triples | Automated: export and validate with `rdflib`; verify triple count matches pipeline output |
| F42 | ALL EntityRuler matches (high and low confidence) display within 3 seconds of upload | Performance test: verify both high-confidence (solid) and low-confidence (dotted) annotations appear |
| F43 | Low-confidence annotations display with distinct visual uncertainty indicator (dotted border, "?" badge, or reduced opacity) | Manual QA: verify visual differentiation from high-confidence annotations |
| F44 | Rejected annotations remain visible in the document with dimmed treatment and "Resurrect" affordance | Manual QA: verify rejected annotations do not disappear; "Resurrect" button accessible |
| F45 | Clicking "Resurrect" opens dual-panel concept selection: Panel A shows EntityRuler's FOLIO tree immediately; Panel B shows Judge's recommendation within 3 seconds | Integration test: trigger resurrection; verify both panels render with correct FOLIO hierarchy trees |
| F46 | User can select any node in either panel's ancestry tree (leaf, parent, child, sibling) to override the Judge | Manual QA: navigate tree in both panels; verify selection updates the annotation |
| F47 | Resurrected annotations carry full provenance: `user_override: true`, EntityRuler original, Judge recommendation, user's selection, and selection source (panel\_a or panel\_b) | Automated: resurrect an annotation; inspect JSON output for complete `user_override_selection` object |
| F48 | "Hide uncertain" toggle switches between "Show all" and "Show confirmed only" | Manual QA: toggle button hides/shows preliminary and rejected annotations |
| F49 | FOLIO labels matching multiple branches display all matching trees in Panel A during resurrection | Integration test: resurrect "Interest" (appears in 3 FOLIO branches); verify Panel A shows 3 trees |
| F50 | `POST /api/annotate/resurrect` endpoint updates persistence and pushes `annotation_resurrected` SSE event | Integration test: call endpoint; verify annotation state changes and SSE event fires |
| F51 | EmbeddingService loads pre-computed FOLIO embeddings from cache in \<1 second when OWL file hash matches | Performance test: measure startup time with existing cache |
| F52 | EmbeddingService rebuilds FOLIO embedding cache when OWL file hash changes | Integration test: modify OWL file; verify cache rebuilds and new vectors differ |
| F53 | Semantic EntityRuler discovers synonym matches: "contractual breach" matches "Breach of Contract" above similarity threshold | Unit test: seed document with known synonyms; verify semantic matches appear |
| F54 | Semantic EntityRuler matches carry `confidence_tier: "semantic"` and `similarity_score` in annotation output | Automated: inspect annotation JSON for semantic match metadata |
| F55 | Semantic EntityRuler matches display with "≈" badge visual indicator, distinct from exact EntityRuler matches | Manual QA: verify visual differentiation between exact and semantic matches |
| F56 | Embedding triage auto-confirms Reconciliation conflicts with similarity \> 0.85 without Judge LLM call | Integration test: inject obvious legal usage; verify no Judge call fires; verify auto-confirm |
| F57 | Embedding triage auto-rejects Reconciliation conflicts with similarity \< 0.50 without Judge LLM call | Integration test: inject obvious non-legal usage; verify no Judge call fires; verify auto-reject |
| F58 | Embedding-augmented resolution catches semantic matches that `rapidfuzz` misses: "property representative" → "Real Estate Broker" | Unit test: verify resolution succeeds via embedding fallback when string similarity \< 0.70 |
| F59 | Embedding provider fallback: if cloud provider unreachable, pipeline automatically uses local model without error | Integration test: configure cloud provider; disable network; verify pipeline completes with local fallback |
| F60 | Embedding cache files are model-specific: switching from `all-mpnet-base-v2` to `voyage-law-2` creates new cache; switching back loads existing cache | Integration test: switch models; verify separate cache files exist; verify load times |
| F61 | Pipeline runs fully offline (no internet) using local embedding model \+ local spaCy models \+ local NuPunkt-RS | Integration test: disable all network access; run pipeline end-to-end; verify completion |
| F62 | Metadata Judge classifies document type from opening text against FOLIO Document Artifacts taxonomy | Integration test: upload Motion to Dismiss; verify `document_metadata.document_type.folio_label` \= "Motion to Dismiss" |
| F62a | Filename pre-classifier extracts document type hints from abbreviated filenames: `mtd.pdf` → "Motion to Dismiss", `NDA_Acme_2025.docx` → "Non-Disclosure Agreement", `motiontodismiss.pdf` → "Motion to Dismiss" | Unit test: run `classify_filename()` against 20+ test filenames covering abbreviations, concatenated words, and date-prefixed names |
| F62b | Filename hint feeds into Metadata Judge prompt as a prior signal; Judge confirms or overrides based on actual document text | Integration test: upload a Reply Brief named `mtd.pdf`; verify Judge classifies as "Reply Brief" (overriding the misleading filename hint) |
| F63 | Metadata Judge distinguishes primary document from attachments: a Motion to Dismiss attaching Exhibit A (contract) classifies as "Motion to Dismiss," not "Contract" | Integration test: upload document with exhibits; verify primary type and attachment types classified separately |
| F64 | Phase 1 extracts caption fields: case number, court, judge, parties with roles | Integration test: upload court filing; verify all caption fields populated |
| F65 | Phase 2 extracts structured fields from targeted sections: signatories from signature block, governing law from boilerplate, claim types from causes of action | Integration test: upload contract and litigation filing; verify section-targeted extraction |
| F66 | Phase 3 annotation promotion: Actor annotations in signature blocks promote to `signatories` metadata; Area of Law annotations in claims sections promote to `claim_types` | Automated: verify promoted annotations appear in `document_metadata` with correct `extraction_method` |
| F67 | Document metadata streams via SSE as `document_metadata` and `document_metadata_update` events during progressive rendering | Integration test: monitor SSE stream; verify Phase 1 metadata arrives before LLM pipeline completes |
| F68 | `GET /api/annotate/metadata/{job_id}` returns document metadata only (type, parties, court, dates, concept summary) | API test: call endpoint; verify response matches metadata schema |
| F69 | `GET /api/annotate/result/{job_id}?format=parquet` returns valid Parquet file with annotation rows \+ document metadata columns | Automated: download Parquet; load with `pyarrow`; verify schema and row count match annotation count |
| F70 | `?format=elasticsearch` returns valid NDJSON ingestible via Elasticsearch `POST _bulk` | Automated: validate NDJSON format; verify each line contains `_index`, `_id`, and annotation fields |
| F71 | `?format=neo4j` returns ZIP containing `nodes.csv`, `relationships.csv`, `documents.csv` following Neo4j import format | Automated: extract ZIP; validate CSV headers match Neo4j `neo4j-admin database import` schema |
| F72 | `?format=rag_chunks` returns chunks with FOLIO concept IRIs, branch tags, and document metadata as filterable fields | Automated: verify each chunk contains `folio_concepts`, `folio_iris`, `folio_branches`, and `document_metadata` |
| F73 | Concept summary statistics include `annotations_by_branch`, `top_concepts` (top 10 with counts), `top_cooccurrence_pairs`, and `top_triples` | Automated: verify `concept_summary` object populated with correct counts matching annotation totals |
| F74 | All Tier 2 export formats carry document metadata (document type, court, parties, case number, dates) alongside annotation data | Automated: export each Tier 2 format; verify metadata fields present |
| F75 | Synthetic document generator produces a realistic Motion to Dismiss when user selects Litigation → Motion to Dismiss | Manual QA: generate document; verify proper caption, legal argument structure, signature block |
| F76 | Synthetic generator respects length parameter: Short (1–5 pages), Medium (10–30 pages), Long (50–100 pages) | Automated: generate each length; verify character count falls within expected range |
| F77 | Synthetic generator applies jurisdiction flavoring: New York federal generates SDNY caption, FRCP references; California state generates Superior Court caption, CCP references | Manual QA: generate same document type with different jurisdictions; verify jurisdiction-appropriate elements |
| F78 | Generated synthetic document feeds directly into the annotation pipeline and produces valid annotations, triples, and metadata | Integration test: generate → annotate → verify complete JSON output with annotations, triples, and document\_metadata |
| F79 | `POST /api/annotate/generate` returns job\_id and SSE stream that emits `synthetic_document` event followed by standard pipeline events | API test: call endpoint; verify SSE stream contains synthetic\_document event before preliminary\_annotations |
| F80 | Document type tree UI displays 9 primary categories; expanding a category reveals subtypes; clicking a subtype selects it | Manual QA: verify tree expand/collapse behavior and selection |
| F81 | Generated synthetic document available for download as `.txt` independently of annotation results | Manual QA: verify download link present after generation completes |

### **11.2 Performance**

| ID | Criterion | Target |
| ----- | ----- | ----- |
| P1 | Processing time for a 100-page document | \< 10 minutes |
| P1a | Processing time for a 500-page document | \< 45 minutes |
| P2 | LLM cost per 100-page document | \< $6.50 (at Claude Sonnet pricing; includes Stage 4 LLM \+ Reconciliation Judge \+ Branch Judge \+ Metadata Judge; reduced by embedding triage) |
| P3 | Annotation precision (% of annotations mapping to correct FOLIO concept) | \> 85% |
| P4 | Annotation recall (% of actual legal concepts tagged) | \> 82% (improved from 80% by Semantic EntityRuler synonym discovery) |
| P5 | FOLIO resolution calls per document | \= unique (concept, branch) pair count (not occurrence count) |
| P6 | Stage 6 string matching for a 500-page document (2.5M chars, 300 patterns) | \< 100ms (Aho-Corasick); \< 2s (regex fallback) |
| P7 | Stage 6 batch string matching for 500 × 100-page documents | \< 10s total (Aho-Corasick); \< 300s (regex fallback) |
| P8 | EntityRuler scan for a 500-page document (2.5M chars, 18K patterns) | \< 5 seconds |
| P9 | Time to first visible annotation after upload | \< 5 seconds (EntityRuler high-confidence results) |
| P10 | Dependency parsing for a 100-page document (\~200 eligible sentences) | \< 15 seconds |
| P11 | NuPunkt-RS sentence detection for a 500-page document (2.5M chars) | \< 100ms |
| P12 | FOLIO embedding cache load from disk (18K vectors, \~28MB) | \< 1 second |
| P13 | FOLIO embedding rebuild (18K labels, local model) | \< 30 seconds |
| P14 | Semantic EntityRuler for a 500-page document (\~50K noun phrases, CPU) | \< 15 seconds |
| P15 | Embedding triage per conflict (1 embed \+ 1 FAISS search) | \< 5ms |
| P16 | Embedding resolution fallback per concept (1 embed \+ 1 FAISS search) | \< 5ms |
| P17 | Metadata Judge Phase 1 (document type classification from first chunks) | \< 10 seconds (returns before LLM pipeline completes) |
| P18 | Metadata Judge Phase 2 (all targeted sections) | \< 20 seconds total |
| P19 | Phase 3 annotation promotion (deterministic scan) | \< 1 second |
| P20 | Parquet export for 500-annotation document | \< 2 seconds |
| P21 | Elasticsearch bulk JSON export for 500-annotation document | \< 1 second |

### **11.3 Non-Functional**

| ID | Criterion |
| ----- | ----- |
| NF1 | Pipeline runs on a single machine (no distributed infrastructure for v1) |
| NF2 | All intermediate artifacts persisted for debugging (canonical text, offset map, raw LLM output, resolution cache) |
| NF3 | Pipeline produces deterministic output for the same input \+ LLM seed |
| NF4 | JSON annotation schema validates against a published JSON Schema |

---

## **12\. Risks and Mitigations**

| Risk | Likelihood | Impact | Mitigation |
| ----- | ----- | ----- | ----- |
| LLM misquotes concept text, causing string-match failure | Medium | Low (missed annotation, not wrong annotation) | Log discards; tune prompt; increase LLM temperature for recall |
| LLM misses a concept entirely across all chunks | Medium | Medium | Future: secondary FOLIO-label scan pass; monitor recall metrics |
| Substring collision ("Landlord" inside "Co-Landlord") | Medium | Low | Aho-Corasick character-class boundary validation (§6.6.6); hyphens treated as word characters so "Co-Landlord" is one word. Regex fallback (§6.6.5) uses equivalent lookbehind/lookahead. |
| PDF line-break normalization incorrectly rejoins intentional short lines | Low | Low | Apply aggressive normalization only to PDF/RTF; skip for Word/Markdown/paste |
| `folio-python` search misses due to label mismatch | Medium | Medium | Fuzzy matching \+ SKOS altLabel; log misses for FOLIO ontology improvement |
| PDF uses scanned images (no text layer) | Medium | High | Docling's built-in OCR; OCR output feeds same normalization pipeline |
| FOLIO branch list evolves | Low | Low | Load branch list dynamically from `folio-python` at startup |
| Legacy `.doc` format extraction fails | Medium | Medium | Fallback chain: antiword → LibreOffice CLI → prompt user to convert to `.docx` |
| Malformed HTML from court-opinion scrapes | High | Low | BeautifulSoup handles broken HTML gracefully; validation report flags anomalies |
| Email contains only images (no text body) | Low | Medium | Detect empty body; fall back to OCR on inline images if available |
| RTF from older DMS contains unusual control sequences | Medium | Low | striprtf2 handles most variants; fallback: LibreOffice CLI conversion |
| Unsupported file format submitted | Low | Low | Format router raises clear error with list of supported formats |
| Pasted text lacks any structural markers | High | Low | Treat as single-section plain text; chunking still works on paragraph boundaries |

---

## **12A. Security Considerations**

### **12A.1 Authentication \+ Authorization**

All `/api/annotate/*` endpoints require authentication. v1 uses API key authentication via the `Authorization: Bearer {api_key}` header, consistent with FOLIO Mapper's existing API pattern. API keys are configured in the environment (`FOLIO_API_KEY`). Unauthenticated requests receive `401 Unauthorized`. Future versions may integrate OAuth 2.0 / OpenID Connect for multi-tenant deployments.

### **12A.2 Upload Limits**

| Constraint | Default | Configurable |
| ----- | ----- | ----- |
| **Maximum file size** | 100 MB | `MAX_UPLOAD_SIZE_MB` env var |
| **Maximum canonical text length** | 10M characters (~2,000 pages) | `MAX_CANONICAL_TEXT_CHARS` env var |
| **Maximum paste text length** | 500K characters (~100 pages) | `MAX_PASTE_TEXT_CHARS` env var |
| **Allowed MIME types** | PDF, DOCX, DOC, MD, TXT, HTML, RTF, EML, MSG | Hardcoded to supported formats |

Files exceeding limits receive `413 Payload Too Large` with a descriptive error message.

### **12A.3 Input Sanitization**

Uploaded files carry security risks:

| Threat | Mitigation |
| ----- | ----- |
| **Malicious PDFs** (embedded JavaScript, exploits) | Docling processes PDFs in a sandboxed parser; no PDF JavaScript execution. Pipeline extracts text only — never renders or executes embedded content. |
| **Zip bombs** (`.docx` is a ZIP archive) | Enforce decompressed size limit (10x compressed size, max 500 MB). Reject files exceeding the limit before extraction. |
| **Path traversal** (filenames like `../../etc/passwd`) | Sanitize uploaded filenames: strip directory components, restrict to alphanumeric + `._-` characters. Uploaded files stored with UUID-based names, never user-supplied paths. |
| **HTML injection** (malicious HTML input) | HTML extractor uses BeautifulSoup in `html.parser` mode (not `lxml` with external entity processing). Script tags stripped during extraction (§6.1.3). |
| **XXE attacks** (XML in DOCX) | python-docx does not resolve external entities by default. No custom XML parsing of user-supplied content. |

### **12A.4 Data Retention \+ Confidentiality**

Law firms and in-house legal departments process privileged and confidential documents. The pipeline:

1. **Deletes uploaded source files** immediately after canonical text assembly (Stage 2). The pipeline retains only the extracted canonical text, never the original file.
2. **Stores all job data locally** — no data leaves the machine unless the user configures a cloud LLM provider (in which case chunk text is sent to the LLM API and subject to that provider's data policies).
3. **Job cleanup** removes all job artifacts after the retention period (§6.0.4).
4. **No telemetry or analytics** — the pipeline sends no usage data to external services.
5. **`DELETE /api/annotate/job/{job_id}`** immediately removes all artifacts for a specific job.

For air-gapped deployments: the pipeline runs fully offline using local LLM (Ollama/LM Studio), local embedding (sentence-transformers), and local NLP models (spaCy, NuPunkt-RS). No internet access required.

### **12A.5 Rate Limiting**

| Endpoint | Default Limit | Purpose |
| ----- | ----- | ----- |
| `POST /api/annotate/upload` | 10 requests/minute | Prevent resource exhaustion from concurrent large uploads |
| `POST /api/annotate/paste` | 30 requests/minute | Allow rapid testing with pasted text |
| `POST /api/annotate/generate` | 5 requests/minute | Limit LLM cost from synthetic generation |
| All other endpoints | 60 requests/minute | General protection |

Rate limits are configurable via environment variables. Exceeded limits receive `429 Too Many Requests` with a `Retry-After` header.

---

## **13\. Future Enhancements (Out of Scope for v1)**

1. \~\~**FOLIO-label scan pass:** After LLM concept discovery, scan the document for all FOLIO labels directly\~\~ — **Implemented in v5.0** as the EntityRuler parallel path (§6.2B)  
2. **Confidence scoring:** Calibrate LLM \+ resolution \+ EntityRuler \+ Judge confidence against human review outcomes  
3. **Active learning:** Feed reviewed unresolved spans back into prompt engineering and FOLIO expansion  
4. **Batch processing API:** Process document portfolios in parallel with progress tracking  
5. **PDF-viewer overlay:** Render annotations on original PDF layout, not just extracted text  
6. **Cross-document analytics:** Aggregate annotations across document sets for concept frequency, co-occurrence, coverage gaps  
7. **Multi-language support:** Leverage FOLIO's multilingual labels for non-English documents  
8. **Additional input formats:** Akoma Ntoso (legal XML), EPUB, ODT (LibreOffice), scanned TIFF/PNG images (direct OCR without PDF wrapper)  
9. **Tier 3 export formats:** spaCy DocBin (Python NLP pipelines), UIMA CAS XMI (enterprise NLP), Protocol Buffers (gRPC microservices), MessagePack (high-performance APIs), Excel (formatted spreadsheet review)  
10. **Drag-and-drop multi-file upload:** Accept a folder or ZIP of mixed-format documents; process each through the format router  
11. **URL ingestion:** Accept a URL (e.g., court opinion on a public website); fetch the page, detect format (HTML), and run through the pipeline  
12. **Coreference resolution:** Integrate `fastcoref` or similar to resolve pronouns ("it," "said Company," "the Plaintiff") to their antecedent entities before annotation  
13. **N-ary relation extraction:** Extend dependency parsing to handle complex events by creating Event Reification nodes in the knowledge graph  
14. **Knowledge graph reasoning:** OWL inference over extracted triples — derive implicit relationships from explicit ones using FOLIO's ontology constraints  
15. **Explicit containment edges:** Add `contained_in` fields to overlapping span annotations (deferred from v4.0)  
16. **Reconciliation learning loop:** Track which EntityRuler matches the Judge consistently confirms or rejects; auto-update confidence tiers  
17. **Embedding-assisted triple validation:** Use embedding similarity to soft-validate SPO triples when FOLIO's domain/range constraints are incomplete  
18. **Cross-document concept deduplication via embeddings:** Cluster semantically equivalent concepts across document portfolios that resolved to different FOLIO IRIs  
19. **Embedding triage threshold auto-calibration:** Track Judge agreement rates with triage decisions; automatically adjust confirm/reject thresholds  
20. **Corpus annotation store:** Centralized queryable database (PostgreSQL) for annotations and triples across all processed documents; enables SQL analytics across the corpus  
21. **Inverted concept index:** FOLIO IRI → \[(doc\_id, position, context)\] for instant concept-based document retrieval across a corpus; powers filtering ("find all Motions to Dismiss for Breach of Contract")  
22. **Batch pipeline:** Process thousands of documents with job queuing, progress tracking, incremental indexing, failure recovery, and cross-document deduplication  
23. **Aggregation API:** Count, percentage, group-by queries over corpus annotations; group by concept, branch, document type, court, jurisdiction, time period  
24. **Co-occurrence API:** Cross-document concept co-occurrence with frequency counts; powers analytics like "which concepts appear together most frequently"  
25. **Graph traversal API:** Follow relation triples from a concept to related concepts across the corpus; Cypher-like query interface over the knowledge graph  
26. **Hierarchy-aware retrieval:** Expand FOLIO IRI to parents, children, and siblings using `folio-python` for broader RAG recall; "Termination" expands to "Expiration," "Rescission," "Cancellation"  
27. **RAG integration endpoints:** Concept-filtered chunk retrieval: `GET /api/retrieve?concept=folio:Actors_Landlord&expand=hierarchy&depth=2`; deterministic graph-following retrieval  
28. **Analytics dashboard:** Visual interface for concept frequency, co-occurrence heatmaps, trend analysis, and relation exploration across a document corpus  
29. **Webhook notifications:** POST to a configured URL when pipeline completes — for headless integration into legal tech document processing pipelines  
30. **SDK / client library:** Python SDK wrapping the API: `client.annotate(file, format="parquet")` — simplifies legal tech integration

---

## **14\. Claude Code Implementation Guide**

This section maps PRD stages to specific files and endpoints in the FOLIO Mapper repository. Claude Code should reference these paths when implementing each stage.

### **14.1 Stage-to-File Mapping**

| PRD Stage | New File to Create | FOLIO Mapper Files to Reuse | Key Endpoint |
| ----- | ----- | ----- | ----- |
| **Stage 1: Ingestion** | `backend/app/services/ingestion/router.py` \+ 10 extractor files (see §5A.4) | `backend/app/services/file_parser.py` (text format patterns) | `POST /api/annotate/upload`, `POST /api/annotate/paste` |
| **Stage 2: Canonical Text** | `backend/app/services/canonical_service.py` | — | (internal, no endpoint) |
| **Stage 2M: Document Metadata** | `backend/app/services/metadata_extractor.py` (new); `backend/app/services/metadata_judge.py` (new) | FOLIO Mapper's LLM abstraction (`backend/app/services/llm/`); `folio-python` (Document Artifacts branch labels) | `GET /api/annotate/metadata/{job_id}`, SSE events `document_metadata` \+ `document_metadata_update` |
| **Synthetic Generator** | `backend/app/services/synthetic_generator.py` (new) | FOLIO Mapper's LLM abstraction (`backend/app/services/llm/`); `folio-python` (Document Artifacts branch for type labels) | `POST /api/annotate/generate` |
| **Path A: EntityRuler** | `backend/app/services/entity_ruler_service.py` | `folio-python` (FOLIO label iteration) | (internal; results stream via SSE) |
| **Path A: Semantic EntityRuler** | `backend/app/services/semantic_entity_ruler.py` | EmbeddingService (shared singleton) | (internal; results stream via SSE) |
| **EmbeddingService** | `backend/app/services/embedding/` (provider dir: `__init__.py`, `local_provider.py`, `openai_provider.py`, `voyage_provider.py`, `cohere_provider.py`, `ollama_provider.py`, `folio_index.py`) | FOLIO Mapper's provider-abstraction pattern (`backend/app/services/llm/`) | (internal singleton; consumed by Semantic EntityRuler, Reconciliation, Resolution, Branch Judge) |
| **Stage 3: Chunking** | `backend/app/services/chunking_service.py` | — | (internal, no endpoint) |
| **NuPunkt-RS Utility** | `backend/app/services/sentence_detector.py` | — | (internal; used by chunker, Judge, dep parser) |
| **Stage 4: LLM Identification** | `backend/app/services/pipeline/annotation_stage.py` | `backend/app/services/llm/` (all provider files) | (internal, calls LLM via existing provider abstraction) |
| **Stage 4.5: Reconciliation** | `backend/app/services/reconciliation_service.py` | `backend/app/services/llm/` (Judge calls) | (internal, no endpoint) |
| **Stage 5: Resolution** | `backend/app/services/resolution_cache.py` | `backend/app/services/folio_service.py` → `search()`, `get_class()`, `get_ancestors()` | `POST /api/mapping/candidates` |
| **Stage 6: String Matching** | `backend/app/services/span_locator.py` | — | (internal, no endpoint) |
| **Stage 6.5: Branch Judge** | `backend/app/services/judge_service.py` | `backend/app/services/llm/` (provider abstraction), `backend/app/services/pipeline/` (Stage 3 Judge pattern) | (internal, no endpoint) |
| **Stage 6.75: Dep. Parsing** | `backend/app/services/relation_extractor.py` | — | (internal; triples delivered via SSE \+ `/api/annotate/triples/`) |
| **Stage 7: Persistence** | `backend/app/models/annotation.py` | `backend/app/services/export_service.py` | `POST /api/annotate/export` |
| **SSE Streaming** | `backend/app/routers/annotation_stream.py` | — | `GET /api/annotate/stream/{job_id}`, `POST /api/annotate/resurrect` |
| **Export** | `backend/app/services/annotation_export_service.py` | `backend/app/services/export_service.py` (reuse file generation patterns), `packages/core/src/folio/` (branch colors for HTML export) | `POST /api/annotate/export`, `POST /api/annotate/batch-export` |

### **14.2 Key Functions in FOLIO Mapper to Call**

**`folio_service.py` — FOLIO singleton and search:**

\# Loading the ontology (already handled by FOLIO Mapper at startup)  
\# See: backend/app/services/folio\_service.py  
folio\_service \= FOLIOService()  \# singleton

\# Search for candidates matching concept text  
\# This is what the resolution cache calls for each unique concept  
candidates \= folio\_service.search\_candidates(  
    text="Landlord",  
    branches=\["Actors"\],  
    top\_n=5  
)  
\# Returns: list of {iri, label, definition, score, branch}

\# Get full concept detail (for annotation enrichment)  
detail \= folio\_service.get\_concept\_detail(iri="folio:R8pNPutX0TN6DlEqkyZuxSw")  
\# Returns: {definition, hierarchy\_path, children, siblings, translations}

\# Get hierarchy path (for annotation provenance)  
ancestors \= folio\_service.get\_ancestors(iri="folio:R8pNPutX0TN6DlEqkyZuxSw")  
\# Returns: \["Legal Concept", "Actors", "Landlord"\]

**`backend/app/services/llm/` — LLM provider abstraction:**

\# The annotation pipeline's Stage 4 prompt runs through the same  
\# provider infrastructure as FOLIO Mapper's mapping pipeline.  
\# See: backend/app/services/llm/ for provider implementations  
\# See: backend/app/routers/llm\_router.py for:  
\#   POST /api/llm/test-connection  
\#   POST /api/llm/models

\# To send the annotation prompt:  
\# 1\. Get the configured provider from FOLIO Mapper's settings  
\# 2\. Call the provider's completion method with the Stage 4 prompt  
\# 3\. Parse the JSON response

**`backend/app/services/pipeline/` — Pipeline orchestration:**

\# FOLIO Mapper's existing pipeline runs Stages 0–3 for taxonomy mapping.  
\# The annotation pipeline adds a new stage file:  
\#   backend/app/services/pipeline/annotation\_stage.py  
\#  
\# This new stage:  
\# 1\. Accepts a chunk\_text and branch\_list  
\# 2\. Builds the Stage 4 prompt (requesting multi-branch classification)  
\# 3\. Calls the LLM via the existing provider abstraction  
\# 4\. Parses the returned JSON \[{"text": "...", "branches": \["...", "..."\]}, ...\]  
\# 5\. Returns the parsed annotations for Stage 5 (which flattens  
\#    multi-branch into per-branch pairs for resolution)

### **14.3 Pydantic Models to Create**

\# backend/app/models/annotation.py

from pydantic import BaseModel  
from enum import Enum

class InputFormat(str, Enum):  
    PDF \= "pdf"  
    DOCX \= "docx"  
    DOC \= "doc"  
    MARKDOWN \= "markdown"  
    PLAIN\_TEXT \= "plain\_text"  
    HTML \= "html"  
    RTF \= "rtf"  
    EML \= "eml"  
    MSG \= "msg"  
    PASTE \= "paste"

class AnnotationPasteRequest(BaseModel):  
    """POST /api/annotate/paste"""  
    text: str  \# pasted content  
    title: str | None \= None  \# optional document title

class AnnotationStatus(BaseModel):  
    """GET /api/annotate/status/{job\_id}"""  
    job\_id: str  
    status: str  \# "processing", "completed", "failed"  
    stage: str   \# current stage name  
    progress: float  \# 0.0–1.0  
    chunks\_processed: int  
    chunks\_total: int  
    source\_format: InputFormat  \# detected input format

class ConceptAnnotation(BaseModel):  
    """Single annotation in the result"""  
    id: str  
    start: int  
    end: int  
    text: str  
    iri: str  
    label: str  
    definition: str  
    branch: str  
    match\_type: str  \# "exact", "fuzzy", "branch\_corrected"  
    provenance: dict

class AnnotationResult(BaseModel):  
    """GET /api/annotate/result/{job\_id}"""  
    document\_id: str  
    source\_format: InputFormat  
    canonical\_text\_hash: str  
    pipeline\_version: str  
    statistics: dict  
    resolution\_cache: list\[dict\]  
    annotations: list\[ConceptAnnotation\]  
    unresolved: list\[dict\]

### **14.4 Router Registration**

Add the new annotation router to FOLIO Mapper's main.py:

\# backend/app/main.py — ADD this import and registration:

from app.routers import annotation\_router

\# In the router registration section:  
app.include\_router(  
    annotation\_router.router,  
    prefix="/api/annotate",  
    tags=\["annotation"\]  
)

### **14.5 Dependencies to Add**

\# backend/pyproject.toml or requirements.txt — ADD:

\# PDF extraction  
docling                    \# IBM's structural PDF extraction (vision models)

\# Word extraction  
python-docx                \# .docx paragraph/table/heading extraction

\# Markdown extraction  
markdown-it-py             \# CommonMark-compliant Markdown parser

\# HTML extraction  
beautifulsoup4             \# Robust HTML tag parsing  
lxml                       \# Fast HTML/XML parser backend for BeautifulSoup

\# RTF extraction  
striprtf2                  \# RTF-to-text conversion

\# Email extraction  
msg-parser                 \# Outlook .msg file parsing (.eml uses stdlib)

\# Format detection  
python-magic               \# MIME type sniffing via libmagic

\# Normalization  
nltk                       \# Word corpus for dehyphenation dictionary

\# Chunking fallback  
langchain-text-splitters   \# RecursiveCharacterTextSplitter for oversized elements

\# Legal sentence boundary detection  
nupunkt                    \# NuPunkt-RS Python binding (Rust backend); \~30M chars/sec  
                           \# Legal-domain trained; 91.1% precision on legal citations

\# EntityRuler \+ Dependency Parsing  
spacy                      \# Industrial NLP: EntityRuler for FOLIO label scan,  
                           \# dependency parsing for SPO triple extraction  
\# Download model after install:  
\#   python \-m spacy download en\_core\_web\_trf  (accuracy, \~25 sent/sec)  
\#   python \-m spacy download en\_core\_web\_sm   (speed, \~200 sent/sec)

\# Interval tree for annotation lookup  
intervaltree               \# O(log n) annotation lookup by character position;  
                           \# used by dependency parser to match tokens to annotations

\# Embedding service (local, default)  
sentence-transformers      \# Local embedding models (all-mpnet-base-v2, etc.)  
                           \# No internet required after initial model download  
faiss-cpu                  \# FAISS nearest-neighbor index for FOLIO label search  
                           \# Use faiss-gpu if GPU available for faster Semantic EntityRuler  
numpy                      \# Vector operations for embedding cache (likely already installed)

\# Embedding service (cloud, optional — install only if using cloud providers)  
\# voyageai                 \# Voyage AI voyage-law-2 (best legal domain embeddings)  
\# openai                   \# Already in FOLIO Mapper — text-embedding-3-small/large  
\# cohere                   \# Cohere embed-english-v3.0

\# Multi-pattern matching  
pyahocorasick              \# C-backed Aho-Corasick automaton for single-pass string matching

\# Streaming delivery  
sse-starlette              \# Server-Sent Events for FastAPI progressive rendering

\# Parquet export (Tier 2\)  
pyarrow                    \# Columnar format for analytics export; legal tech integration

\# Export formats  
pyld                       \# JSON-LD processing for W3C Web Annotation export  
rdflib                     \# RDF/Turtle serialization (may already be in FOLIO Mapper)

FOLIO Mapper already includes: `folio-python`, `rapidfuzz`, `openai`, `anthropic`, `httpx`, `fastapi`, `pydantic`.

### **10.1 System Requirements \+ Memory Footprint**

The pipeline loads several large models and data structures into memory simultaneously. Minimum system requirements for v1:

| Component | Approximate Memory | Loaded When |
| ----- | ----- | ----- |
| **spaCy `en_core_web_trf`** | ~500 MB | Startup (dependency parsing) |
| **spaCy `en_core_web_sm`** (alternative) | ~15 MB | Startup (if speed mode selected) |
| **sentence-transformers `all-mpnet-base-v2`** | ~420 MB | Startup (EmbeddingService) |
| **EntityRuler with 18K patterns** | ~50 MB | Startup (spaCy EntityRuler) |
| **FAISS index (18K × 768d)** | ~55 MB | Startup (FOLIO embedding index) |
| **FOLIO ontology (`folio-python`)** | ~30 MB | Startup (shared singleton) |
| **NuPunkt-RS model** | ~5 MB | Startup (sentence detector) |
| **Per-document canonical text** | ~2.5 MB per 500 pages | Per-job, released on completion |
| **Per-document annotations** | ~5-20 MB per 500 pages | Per-job, released on completion |
| **Python runtime + FastAPI** | ~100 MB | Always |
| **Total (baseline, `en_core_web_trf`)** | **~1.2 GB** | At startup |
| **Total (baseline, `en_core_web_sm`)** | **~700 MB** | At startup |
| **Per concurrent job** | **~10-30 MB** | During processing |

**Minimum requirements:** 4 GB RAM (single concurrent job with `en_core_web_sm`), 8 GB RAM recommended (3 concurrent jobs with `en_core_web_trf`). No GPU required — all models run on CPU. GPU accelerates spaCy transformer and sentence-transformers if available.

**Lazy loading option:** For memory-constrained environments, spaCy's `en_core_web_trf` model can load on first dependency-parsing request rather than at startup, reducing baseline memory to ~700 MB. The first dependency parse request incurs a ~5-second model load delay.

---

## **15\. Glossary**

| Term | Definition |
| ----- | ----- |
| **Canonical text** | The single, immutable string assembled from all normalized document elements — regardless of source format. Every character offset references this string. |
| **TextElement** | The universal intermediate representation produced by every format-specific extractor. Contains text, element type, section path, page number, and source format. Stages 2–7 operate exclusively on TextElement lists. |
| **Format router** | The ingestion entry point that detects input format (via extension, MIME type, or paste flag) and dispatches to the correct extractor. See `backend/app/services/ingestion/router.py`. |
| **Normalization severity** | The aggressiveness level applied to text cleanup, calibrated per source format: aggressive (PDF), moderate (HTML/RTF), light (Word/text/email), minimal (Markdown/paste). |
| **Resolution cache** | A dictionary mapping each unique (concept\_text, branch) pair to its FOLIO Mapper resolution result. Built once, applied to all occurrences. |
| **Standoff annotation** | A format where annotations are stored separately from the source text, referencing it by character offsets. Contrasts with inline annotation, where annotations are embedded within the text (e.g., HTML `<span>` tags). JSON, XML, brat, and JSONL exports use standoff; HTML export uses inline. |
| **W3C Web Annotation** | A W3C Recommendation (`https://www.w3.org/TR/annotation-model/`) specifying a JSON-LD data model for annotation interchange. Uses `TextPositionSelector` (character offsets) and `TextQuoteSelector` (exact match \+ prefix/suffix) to anchor annotations to text. |
| **Lossless export** | An export format that preserves full annotation fidelity: every field, relationship, and metadata element survives the conversion. JSON, JSON-LD, XML, and RDF/Turtle qualify. |
| **Lossy export** | An export format that sacrifices some annotation detail for compatibility or readability. CSV flattens nested structures; brat drops definitions; HTML optimizes for human viewing. |
| **Overlapping spans** | Two or more annotations whose character ranges intersect. Occurs when a contained concept (e.g., "Contract" at 111–119) sits inside a container concept (e.g., "Breach of Contract" at 100–119). The pipeline produces overlapping spans intentionally — each annotation is independent in a flat array, and containment relationships are derivable from the offsets. |
| **FOLIO Mapper** | The existing tool ([`damienriehl/folio-mapper`](https://github.com/damienriehl/folio-mapper)) that maps user taxonomies to FOLIO using fuzzy matching \+ optional LLM ranking. This annotation pipeline extends FOLIO Mapper's backend. |
| **FOLIO** | Federated Open Legal Information Ontology — 18,000+ legal concepts in a hierarchical tree, CC-BY licensed |
| **FOLIO branch** | A top-level category in the FOLIO hierarchy (e.g., "Area of Law," "Actors," "Contractual Clause") |
| **IRI** | Internationalized Resource Identifier — FOLIO's unique ID for each concept |
| **Soft wrap** | An artificial line break inserted by a PDF renderer to fit column width; carries no semantic meaning |
| **Dehyphenation** | Removing a hyphen at a line break to rejoin a split word ("indemni-" \+ "fication" → "indemnification") |
| **Resolve once, use many** | The pattern of resolving each unique concept against `folio-python` exactly once, then stamping that resolution onto every occurrence in the document |
| **folio-python** | The official Python library for querying the FOLIO ontology |
| **Annotation layer** | The JSON structure containing all resolved span annotations for a document |
| **Dual-path discovery** | The architecture where two independent systems (EntityRuler \+ LLM) identify concepts in parallel, with zero mutual awareness, and a Reconciliation Layer merges their outputs |
| **EntityRuler** | A spaCy pipeline component that matches text against a dictionary of known patterns (here, 18,000+ FOLIO labels). Deterministic, fast, context-blind. |
| **Reconciliation Layer** | The component that merges EntityRuler and LLM results, categorizes matches into five categories (A–E), and routes conflicts to the Reconciliation Judge |
| **Reconciliation Judge** | An LLM that resolves conflicts between EntityRuler and LLM results by reading surrounding context. Determines whether a matched FOLIO label functions as a legal concept in its specific sentence. |
| **Confidence tier** | Classification of EntityRuler matches as "high" (multi-word labels, legal-specific single words) or "low" (common English words matching FOLIO labels). High-confidence matches render immediately as preliminary annotations; low-confidence matches await Judge confirmation. |
| **NuPunkt-RS** | A Rust-backed sentence boundary detector trained on legal corpora. Achieves 91.1% precision on legal text by correctly handling citations like "123 F.2d 456." Processes \~30M chars/sec. |
| **Progressive rendering** | The UX pattern where annotations appear incrementally: EntityRuler results within seconds, LLM results per-chunk, Judge updates as reconciliation completes. Delivered via Server-Sent Events (SSE). |
| **Server-Sent Events (SSE)** | A one-directional HTTP streaming protocol where the server pushes events to the client. Used for progressive annotation delivery. Simpler than WebSockets; sufficient because the pipeline streams to the user, not vice versa. |
| **SPO triple** | A Subject-Predicate-Object tuple representing a relationship in the knowledge graph. Example: (folio:Court, folio:Denied, folio:Motion). Extracted by the dependency parser from sentences containing 2+ FOLIO concepts. |
| **Dependency parsing** | Syntactic analysis that identifies grammatical relationships (subject, verb, object) in a sentence. spaCy's dependency parser produces the tree structure from which SPO triples are extracted. |
| **Knowledge Graph** | A structured network of entities (nodes) connected by semantic relationships (edges). The pipeline's span annotations become nodes; dependency-parsed triples become edges. FOLIO IRIs provide the vocabulary. |
| **FOLIO verb** | A FOLIO ontology concept representing an action or event (e.g., "denied," "overruled," "drafted," "signed"). FOLIO verbs serve as predicates (edges) in the knowledge graph, connecting subject entities to object entities. |
| **Annotation state** | One of three lifecycle states: **preliminary** (EntityRuler matched, awaiting LLM reconciliation), **confirmed** (pipeline verified or user resurrected), or **rejected** (Judge disagreed — dimmed but visible, user can resurrect). |
| **User resurrection** | The act of overriding a Judge's rejection by clicking "Resurrect" on a rejected annotation. Opens a dual-panel FOLIO tree selection using FOLIO Mapper's existing tree component. The user selects the correct concept from either the EntityRuler's original match tree or the Judge's contextual recommendation tree. Full provenance is preserved. |
| **Dual-panel concept selection** | The resurrection UI that displays two FOLIO ancestry trees side-by-side: Panel A (EntityRuler's original match, immediate) and Panel B (Judge's contextual recommendation, 1–3 second LLM call). The user clicks any node in either tree to finalize the annotation. |
| **EmbeddingService** | A shared singleton that provides pre-computed FOLIO label embeddings and on-demand text embedding to multiple pipeline stages. Runs locally by default (`all-mpnet-base-v2`, no internet) with optional cloud providers. Loads FOLIO embeddings from a hash-keyed disk cache; rebuilds only when the FOLIO OWL file updates. |
| **Embedding triage** | The pattern of using embedding similarity to auto-resolve obvious Reconciliation and Branch Judge conflicts before sending them to an LLM Judge. High similarity (\>0.85) → auto-confirm. Low similarity (\<0.50) → auto-reject. Ambiguous (0.50–0.85) → send to Judge. Saves \~30–60% of Judge token cost. |
| **Semantic EntityRuler** | An extension of Path A that discovers FOLIO concepts via embedding similarity rather than exact string matching. Extracts noun phrases from the document, embeds them, and finds nearest FOLIO labels in the pre-computed embedding index. Catches synonyms ("contractual breach" → "Breach of Contract") and paraphrases the literal EntityRuler misses. |
| **FAISS** | Facebook AI Similarity Search — a library for efficient nearest-neighbor search in high-dimensional vector spaces. The pipeline uses a FAISS index to search 18,000+ FOLIO label embeddings in \<1ms per query. |
| **Cosine similarity** | A measure of directional similarity between two vectors, ranging from \-1 (opposite) to 1 (identical). The pipeline uses cosine similarity on normalized embedding vectors to compare document text against FOLIO concept definitions. |
| **Embedding provider** | An adapter implementing the `EmbeddingProvider` interface. Available providers: LocalProvider (sentence-transformers, default), OllamaProvider, VoyageProvider, OpenAIProvider, CohereProvider. Follows FOLIO Mapper's LLM provider-abstraction pattern. |
| **Document Metadata Extraction** | A three-phase process that extracts structured document-level metadata (document type, court, judge, parties, case number, dates, claim types, outcome) from the document. Phase 1: Metadata Judge classifies the document type from the opening text. Phase 2: Metadata Judge extracts structured fields from targeted sections (signature blocks, governing law clauses, holdings). Phase 3: Deterministic annotation promotion based on structural position. |
| **Metadata Judge** | An LLM Judge that classifies the document type against FOLIO's Document Artifacts taxonomy and extracts structured metadata fields from targeted document sections. Distinct from the Reconciliation Judge and Branch Judge. Runs early in the pipeline (after first chunks available). |
| **Annotation promotion** | The deterministic process of promoting a body annotation to a document-level metadata field based on its structural position. An "Actor" annotation in a signature block becomes a `signatory` metadata field. An "Area of Law" annotation in a claims section becomes a `claim_type` metadata field. No LLM calls — purely position-based. |
| **Concept summary** | A document-level statistical profile: annotations by branch, top 10 concepts with counts, top co-occurrence pairs (concepts appearing in the same sentence), and top SPO triples. Included in every export format. |
| **Parquet export** | Columnar analytics format. One row per annotation with document metadata denormalized onto every row. Legal tech companies concatenate per-document Parquet files into corpus-level analytics datasets. |
| **Elasticsearch bulk JSON** | NDJSON format directly ingestible via Elasticsearch's `POST _bulk` API. Each annotation becomes a searchable document with FOLIO IRI and branch facets. |
| **Neo4j CSV bundle** | Three CSV files (nodes, relationships, documents) following Neo4j's `neo4j-admin database import` format for direct graph database import. |
| **RAG-ready chunk JSON** | Stage 3 chunks enriched with FOLIO concept IRIs, branch tags, and document metadata as filterable fields. Enables deterministic concept-filtered retrieval in vector stores (ChromaDB, Pinecone, Weaviate) — graph-following retrieval, not purely probabilistic embedding search. |
| **Synthetic document generator** | A feature that produces realistic synthetic legal documents for pipeline testing without requiring real client data. The user selects a document type from a categorized tree (9 categories, \~45 subtypes), length (short/medium/long), and optional jurisdiction. The LLM generates a properly structured document with natural legal terminology, fictional parties, and jurisdiction-appropriate references. The generated text feeds directly into the annotation pipeline. |

