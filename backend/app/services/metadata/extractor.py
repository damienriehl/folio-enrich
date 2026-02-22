from __future__ import annotations

import logging

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """You are a legal metadata extractor. Given the document type and text, extract structured fields.

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
{{"court": "", "judge": "", "case_number": "", "parties": [], "date_filed": "", "jurisdiction": "", "governing_law": "", "claim_types": []}}

DOCUMENT TEXT:
{text}"""


class MetadataExtractor:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def extract(self, text: str, doc_type: str) -> dict:
        # Use first 2000 chars for extraction
        snippet = text[:2000]
        prompt = EXTRACT_PROMPT.replace("{doc_type}", doc_type).replace("{text}", snippet)
        try:
            return await self.llm.structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "court": {"type": "string"},
                        "judge": {"type": "string"},
                        "case_number": {"type": "string"},
                        "parties": {"type": "array", "items": {"type": "string"}},
                        "date_filed": {"type": "string"},
                        "jurisdiction": {"type": "string"},
                        "governing_law": {"type": "string"},
                        "claim_types": {"type": "array", "items": {"type": "string"}},
                    },
                },
            )
        except Exception:
            logger.exception("Metadata extraction failed")
            return {}
