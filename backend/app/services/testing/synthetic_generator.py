from __future__ import annotations

import logging

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

SYNTHETIC_PROMPT = """Generate a realistic synthetic legal document with the following specifications:

Document Type: {doc_type}
Length: {length} (short=1-2 pages, medium=3-5 pages, long=8-15 pages)
Jurisdiction: {jurisdiction}

Requirements:
- Use realistic but fictional names, dates, and case numbers
- Include proper legal formatting and structure
- Include relevant legal concepts and terminology
- Do NOT use real case names or real people

Generate ONLY the document text, no explanations."""

DOC_TYPES = {
    "Litigation": [
        "Motion to Dismiss", "Complaint", "Answer", "Motion for Summary Judgment",
        "Memorandum of Law", "Court Opinion",
    ],
    "Contracts": [
        "Commercial Lease", "Employment Agreement", "NDA",
        "Purchase Agreement", "Service Agreement",
    ],
    "Corporate": [
        "Board Resolution", "Bylaws Amendment", "Shareholder Agreement",
        "Operating Agreement",
    ],
    "Regulatory": [
        "Compliance Report", "Regulatory Filing", "Agency Opinion",
    ],
    "Law Firm Operations": [
        "Engagement Letter", "Legal Opinion Letter",
    ],
    "Real Estate": [
        "Deed of Trust", "Purchase and Sale Agreement", "Lease Agreement",
    ],
    "IP": [
        "Patent License Agreement", "Trademark Assignment",
    ],
    "Estate Planning": [
        "Last Will and Testament", "Trust Agreement",
    ],
    "Immigration": [
        "Immigration Petition", "Visa Application Support Letter",
    ],
}


class SyntheticGenerator:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def generate(
        self,
        doc_type: str = "Motion to Dismiss",
        length: str = "medium",
        jurisdiction: str = "Federal",
    ) -> str:
        prompt = SYNTHETIC_PROMPT.replace("{doc_type}", doc_type)
        prompt = prompt.replace("{length}", length)
        prompt = prompt.replace("{jurisdiction}", jurisdiction)
        return await self.llm.complete(prompt)

    @staticmethod
    def list_doc_types() -> dict[str, list[str]]:
        return DOC_TYPES
