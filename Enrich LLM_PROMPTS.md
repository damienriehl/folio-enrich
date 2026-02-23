# FOLIO Enrich — All LLM Prompts

This document contains every LLM prompt in the codebase, organized by pipeline stage. Edit prompts directly in the source files referenced below.

---

## Table of Contents

1. [Concept Identification Prompt](#1-concept-identification-prompt) — LLM stage: extract legal concepts from text chunks
2. [Branch Judge Prompt](#2-branch-judge-prompt) — Branch Judge stage: disambiguate FOLIO branch for a concept
3. [Document Classifier Prompt](#3-document-classifier-prompt) — Metadata stage: classify document type
4. [Metadata Extraction Prompt](#4-metadata-extraction-prompt) — Metadata stage: extract structured fields
5. [Synthetic Document Generation Prompt](#5-synthetic-document-generation-prompt) — `/synthetic` endpoint: generate test documents
6. [JSON Schema Instruction (appended automatically)](#6-json-schema-instruction) — Appended to all `structured()` calls
7. [FOLIO Branch List (shared constant)](#7-folio-branch-list) — Injected into prompts 1 and 2

---

## 1. Concept Identification Prompt

**File:** `backend/app/services/llm/prompts/concept_identification.py` (lines 5–26)
**Called by:** `backend/app/services/concept/llm_concept_identifier.py` → `build_concept_identification_prompt(chunk.text)`
**LLM method:** `self.llm.structured()` with JSON schema
**Pipeline stage:** LLM Concept Identification (runs in parallel with EntityRuler)

```text
You are a legal concept annotator. Given a chunk of legal text, identify every legal concept that appears in the text.

For each concept found, provide:
1. **concept_text**: The exact text span as it appears in the document
2. **branch_hint**: Which FOLIO ontology branch this concept most likely belongs to
3. **confidence**: Your confidence (0.0-1.0) that this is a legal concept

FOLIO ontology branches:
- Legal Actors
- Legal Analytics
- Legal Areas
- Legal Authorities
- Legal Communication
- Legal Concepts
- Legal Document Artifacts
- Legal Duties
- Legal Education
- Legal Entities
- Legal Ethics
- Legal Events
- Legal Governance
- Legal Industry
- Legal Informatics
- Legal Instruments
- Legal Jurisdictions
- Legal Matter Lifecycle
- Legal Practice Areas
- Legal Processes
- Legal Professional Development
- Legal Rights
- Legal Standards
- Legal Technology

Rules:
- Include both explicit legal terms (e.g., "breach of contract") and contextual legal concepts (e.g., "damages" when used in a legal sense)
- Use the EXACT text as it appears — do not paraphrase or normalize
- A concept can be 1-5 words long
- Prefer the most specific concept (e.g., "breach of contract" over just "breach")
- Do not include common English words that are not legal concepts in context

Respond with JSON:
{"concepts": [{"concept_text": "...", "branch_hint": "...", "confidence": 0.95}]}

TEXT:
{text}
```

**Template variables:**
- `{text}` — the document chunk text (replaced at call time)

---

## 2. Branch Judge Prompt

**File:** `backend/app/services/concept/branch_judge.py` (lines 11–22)
**Called by:** `branch_judge.py` → `judge(concept_text, sentence, candidate_branches)`
**LLM method:** `self.llm.structured()` with JSON schema
**Pipeline stage:** Branch Judge (resolves ambiguous branch assignments)

```text
You are a legal ontology expert. Given a concept that appears in a sentence, determine which FOLIO ontology branch it belongs to.

FOLIO branches:
- Legal Actors
- Legal Analytics
- Legal Areas
- Legal Authorities
- Legal Communication
- Legal Concepts
- Legal Document Artifacts
- Legal Duties
- Legal Education
- Legal Entities
- Legal Ethics
- Legal Events
- Legal Governance
- Legal Industry
- Legal Informatics
- Legal Instruments
- Legal Jurisdictions
- Legal Matter Lifecycle
- Legal Practice Areas
- Legal Processes
- Legal Professional Development
- Legal Rights
- Legal Standards
- Legal Technology

Given:
- **concept**: {concept_text}
- **sentence**: {sentence}
- **candidate_branches**: {candidates}

Pick the SINGLE best branch. Respond with JSON:
{"branch": "...", "confidence": 0.95, "reasoning": "..."}
```

**Template variables:**
- `{concept_text}` — the concept being judged
- `{sentence}` — the sentence context where the concept appears
- `{candidates}` — comma-separated list of candidate branches

---

## 3. Document Classifier Prompt

**File:** `backend/app/services/metadata/classifier.py` (lines 9–25)
**Called by:** `classifier.py` → `classify(text)` (uses first 500 characters)
**LLM method:** `self.llm.structured()` with JSON schema
**Pipeline stage:** Metadata Extraction

```text
You are a legal document classifier. Given the beginning of a document, classify its type.

Common legal document types:
- Motion to Dismiss, Motion for Summary Judgment, Motion in Limine
- Complaint, Answer, Counterclaim
- Commercial Lease, Employment Agreement, NDA, Purchase Agreement
- Court Opinion, Order, Judgment
- Memorandum of Law, Brief, Legal Memorandum
- Deposition Transcript, Affidavit, Declaration
- Statute, Regulation, Administrative Rule
- Contract Amendment, Settlement Agreement

Respond with JSON:
{"document_type": "...", "confidence": 0.95, "reasoning": "..."}

DOCUMENT TEXT (first 500 chars):
{text}
```

**Template variables:**
- `{text}` — first 500 characters of the document

---

## 4. Metadata Extraction Prompt

**File:** `backend/app/services/metadata/extractor.py` (lines 9–27)
**Called by:** `extractor.py` → `extract(text, doc_type)` (uses first 2000 characters)
**LLM method:** `self.llm.structured()` with JSON schema
**Pipeline stage:** Metadata Extraction (runs after document classification)

```text
You are a legal metadata extractor. Given the document type and text, extract structured fields.

Document type: {doc_type}

Extract these fields (leave empty string if not found):
- court: The court name
- judge: The judge name
- case_number: The case/docket number
- parties: List of parties (plaintiff, defendant, etc.)
- date_filed: Filing date
- jurisdiction: Jurisdiction
- governing_law: Governing law clause
- claim_types: Types of claims

Respond with JSON:
{"court": "", "judge": "", "case_number": "", "parties": [], "date_filed": "", "jurisdiction": "", "governing_law": "", "claim_types": []}

DOCUMENT TEXT:
{text}
```

**Template variables:**
- `{doc_type}` — the classified document type (from prompt 3)
- `{text}` — first 2000 characters of the document

---

## 5. Synthetic Document Generation Prompt

**File:** `backend/app/services/testing/synthetic_generator.py` (lines 9–21)
**Called by:** `synthetic_generator.py` → `generate(doc_type, length, jurisdiction)`
**LLM method:** `self.llm.complete()` (free-text response, not structured JSON)
**Endpoint:** `POST /synthetic`

```text
Generate a realistic synthetic legal document with the following specifications:

Document Type: {doc_type}
Length: {length} (short=1-2 pages, medium=3-5 pages, long=8-15 pages)
Jurisdiction: {jurisdiction}

Requirements:
- Use realistic but fictional names, dates, and case numbers
- Include proper legal formatting and structure
- Include relevant legal concepts and terminology
- Do NOT use real case names or real people

Generate ONLY the document text, no explanations.
```

**Template variables:**
- `{doc_type}` — e.g., "Motion to Dismiss", "Commercial Lease", "Court Opinion"
- `{length}` — `short`, `medium`, or `long`
- `{jurisdiction}` — e.g., "Federal", "New York", "Delaware"

**Available document types** (defined in same file, lines 23–54):

| Category | Types |
|---|---|
| Litigation | Motion to Dismiss, Complaint, Answer, Motion for Summary Judgment, Memorandum of Law, Court Opinion |
| Contracts | Commercial Lease, Employment Agreement, NDA, Purchase Agreement, Service Agreement |
| Corporate | Board Resolution, Bylaws Amendment, Shareholder Agreement, Operating Agreement |
| Regulatory | Compliance Report, Regulatory Filing, Agency Opinion |
| Law Firm Operations | Engagement Letter, Legal Opinion Letter |
| Real Estate | Deed of Trust, Purchase and Sale Agreement, Lease Agreement |
| IP | Patent License Agreement, Trademark Assignment |
| Estate Planning | Last Will and Testament, Trust Agreement |
| Immigration | Immigration Petition, Visa Application Support Letter |

---

## 6. JSON Schema Instruction

**Appended automatically** by `structured()` in Anthropic, Cohere, and Google providers.
**Not appended** by the OpenAI provider (uses `response_format={"type": "json_object"}` instead).

**Files:**
- `backend/app/services/llm/anthropic_provider.py` (lines 71–73)
- `backend/app/services/llm/cohere_provider.py` (lines 62–64)
- `backend/app/services/llm/google_provider.py` (lines 78–80)

```text
Respond ONLY with valid JSON matching this schema:
{schema_json}
```

This text is appended to prompts 1–4 whenever they are sent via `structured()`. The `{schema_json}` is the pretty-printed JSON schema passed to the method.

---

## 7. FOLIO Branch List

**File:** `backend/app/services/llm/prompts/templates.py` (lines 3–30)
**Used by:** Prompts 1 and 2 (injected at import time via f-string)

```text
- Legal Actors
- Legal Analytics
- Legal Areas
- Legal Authorities
- Legal Communication
- Legal Concepts
- Legal Document Artifacts
- Legal Duties
- Legal Education
- Legal Entities
- Legal Ethics
- Legal Events
- Legal Governance
- Legal Industry
- Legal Informatics
- Legal Instruments
- Legal Jurisdictions
- Legal Matter Lifecycle
- Legal Practice Areas
- Legal Processes
- Legal Professional Development
- Legal Rights
- Legal Standards
- Legal Technology
```

---

## 8. Test Connection Prompts

Minimal prompts used only for LLM provider connectivity testing. Not part of the pipeline.

| Provider | File | Message |
|---|---|---|
| Anthropic | `backend/app/services/llm/anthropic_provider.py:90` | `"Hi"` |
| OpenAI-compat | `backend/app/services/llm/openai_compat.py:70` | `"Hi"` |
| Cohere | `backend/app/services/llm/cohere_provider.py:79` | `"Hi"` |
| Google | `backend/app/services/llm/google_provider.py:95` | `"Hi"` |

---

## Pipeline Flow

```
Document Input
    │
    ├─ [Prompt 3] Document Classifier → document_type
    ├─ [Prompt 4] Metadata Extractor  → court, judge, parties, etc.
    │
    ├─ EntityRuler (no LLM — pattern matching)
    ├─ [Prompt 1] Concept Identification → concepts per chunk
    │
    ├─ Reconciliation (no LLM — merges ruler + LLM results)
    ├─ Resolution (no LLM — FOLIO ontology lookup)
    ├─ String Matching (no LLM — Aho-Corasick)
    ├─ [Prompt 2] Branch Judge → disambiguate branches
    ├─ Dependency Parsing (no LLM — spaCy)
    │
    └─ Export
```
