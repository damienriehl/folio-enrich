from __future__ import annotations

from app.services.llm.prompts.templates import BRANCH_LIST

CONCEPT_IDENTIFICATION_PROMPT = f"""You are a legal concept annotator. Given a chunk of legal text, identify every legal concept that appears in the text.

For each concept found, provide:
1. **concept_text**: The exact text span as it appears in the document
2. **branch_hint**: Which FOLIO ontology branch this concept most likely belongs to
3. **confidence**: Your confidence (0.0-1.0) that this is a legal concept

FOLIO ontology branches:
{BRANCH_LIST}

Rules:
- Include both explicit legal terms (e.g., "breach of contract") and contextual legal concepts (e.g., "damages" when used in a legal sense)
- Use the EXACT text as it appears — do not paraphrase or normalize
- A concept can be 1-5 words long
- Prefer the most specific concept (e.g., "breach of contract" over just "breach")
- Do not include common English words that are not legal concepts in context
- Do NOT identify "area of law" categories (e.g., "litigation", "corporate law", "real estate law") — these are document-level classifications, not text-level concepts

Respond with JSON:
{{"concepts": [{{"concept_text": "...", "branch_hint": "...", "confidence": 0.95}}]}}

TEXT:
{{text}}"""


def build_concept_identification_prompt(text: str) -> str:
    return CONCEPT_IDENTIFICATION_PROMPT.replace("{text}", text)
