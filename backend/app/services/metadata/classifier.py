from __future__ import annotations

import logging

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """You are a legal document classifier. Given the beginning of a document, classify its type.

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
{{"document_type": "...", "confidence": 0.95, "reasoning": "..."}}

DOCUMENT TEXT (first 500 chars):
{text}"""


class DocumentClassifier:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def classify(self, text: str) -> dict:
        snippet = text[:500]
        prompt = CLASSIFY_PROMPT.replace("{text}", snippet)
        try:
            return await self.llm.structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "document_type": {"type": "string"},
                        "confidence": {"type": "number"},
                        "reasoning": {"type": "string"},
                    },
                },
            )
        except Exception:
            logger.exception("Document classification failed")
            return {"document_type": "Unknown", "confidence": 0.0, "reasoning": "error"}
