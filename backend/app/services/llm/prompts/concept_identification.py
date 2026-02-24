from __future__ import annotations

from app.services.llm.prompts.templates import BRANCH_LIST, get_branch_detail

# Template uses {branch_info} placeholder to be filled at call time
_CONCEPT_IDENTIFICATION_TEMPLATE = """You are a legal concept annotator. Given a chunk of legal text, identify every legal concept that appears in the text.

For each concept found, provide:
1. **concept_text**: The exact text span as it appears in the document
2. **branch_hints**: A list of FOLIO ontology branches (1-3, most likely first) this concept belongs to
3. **confidence**: Your confidence (0.0-1.0) that this is a legal concept

FOLIO ontology branches (with representative concepts and definitions):
{branch_info}

Rules:
- Include both explicit legal terms (e.g., "breach of contract") and contextual legal concepts (e.g., "damages" when used in a legal sense)
- Use the EXACT text as it appears — do not paraphrase or normalize
- A concept can be 1-5 words long
- Prefer the most specific concept (e.g., "breach of contract" over just "breach")
- Do not include common English words that are not legal concepts in context
- Do NOT identify "area of law" categories (e.g., "litigation", "corporate law", "real estate law") — these are document-level classifications, not text-level concepts

Respond with JSON:
{{"concepts": [{{"concept_text": "...", "branch_hints": ["...", "..."], "confidence": 0.95}}]}}

TEXT:
{text}"""


def build_concept_identification_prompt(text: str) -> str:
    branch_info = get_branch_detail()
    return (
        _CONCEPT_IDENTIFICATION_TEMPLATE
        .replace("{branch_info}", branch_info)
        .replace("{text}", text)
    )
