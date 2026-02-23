from __future__ import annotations

AREA_OF_LAW_PROMPT = """You are a legal document classifier. Based on the document metadata and concepts already extracted from a legal document, classify which areas of law (practice areas) the document relates to.

Document information:
- Document type: {document_type}
- Extracted fields: {extracted_fields}
- Key concepts found: {concepts_summary}

Classify the document into one or more areas of law. For each area, provide:
1. **area**: The practice area name (e.g., "Litigation", "Corporate / M&A", "Real Estate", "Employment Law", "Intellectual Property", "Regulatory / Compliance", "Tax", "Bankruptcy / Insolvency", "Environmental Law", "Family Law", "Criminal Law", "Immigration", "Healthcare Law", "Securities", "Antitrust", "International Trade", "Insurance", "Banking / Finance", "Government Contracts", "Privacy / Data Protection")
2. **confidence**: Your confidence (0.0-1.0) that this area of law applies
3. **reasoning**: Brief explanation of why this area applies

Only include areas with confidence >= 0.5. Order by confidence descending.

Respond with JSON:
{{"areas": [{{"area": "...", "confidence": 0.95, "reasoning": "..."}}]}}"""


def build_area_of_law_prompt(
    document_type: str,
    extracted_fields: dict,
    concepts_summary: str,
) -> str:
    return (
        AREA_OF_LAW_PROMPT
        .replace("{document_type}", document_type)
        .replace("{extracted_fields}", str(extracted_fields))
        .replace("{concepts_summary}", concepts_summary)
    )
