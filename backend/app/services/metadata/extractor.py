from __future__ import annotations

import logging

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """You are a legal metadata extractor. A pipeline has already extracted entities, relationships, and concepts from the entire document. Use this structured context plus the document bookends to extract metadata fields.

Document type: {doc_type}

{context_block}

For each field below, extract the value from the context above. Leave empty string "" or empty list [] if not found. Do NOT invent information — only extract what is supported by the context.

Fields:
- case_name: Full case name (e.g., "Acme Corp v. Widget Inc")
- court: Court name
- judge: Judge name(s)
- case_number: Case/docket number
- parties: List of parties with roles (e.g., "Acme Corp (Plaintiff)")
- jurisdiction: Jurisdiction (e.g., "Federal", "State — New York")
- procedural_posture: Current procedural stage (e.g., "Motion to Dismiss pending")
- cause_of_action: Legal basis for the claim (e.g., "42 U.S.C. § 1983")
- claim_types: Types of claims (e.g., "Breach of Contract", "Negligence")
- relief_sought: What relief is requested (e.g., "Damages of $5,000,000", "Injunctive relief")
- disposition: Outcome if stated (e.g., "Granted", "Denied", "Settled")
- standard_of_review: Legal standard applied (e.g., "de novo", "abuse of discretion")
- governing_law: Governing law clause or applicable law
- author: Document author
- recipient: Document recipient
- attorneys: List of attorneys with affiliation (e.g., "John Smith (Smith & Jones LLP, for Plaintiff)")
- signatories: List of signatories
- witnesses: List of witnesses, deponents, or affiants
- date_filed: Filing date
- date_signed: Date signed
- date_effective: Effective date
- date_due: Due date or deadline
- dates_mentioned: List of other significant dates with context (e.g., "2024-01-15: date of incident")
- document_title: Formal title of the document
- docket_entry_number: Docket entry number if any
- related_documents: List of referenced documents (e.g., "Exhibit A — Purchase Agreement")
- confidentiality: Confidentiality markings (e.g., "CONFIDENTIAL — ATTORNEY-CLIENT PRIVILEGED")
- contract_type: Type of contract if applicable (e.g., "Employment Agreement", "NDA")
- counterparties: List of contracting parties
- term_duration: Contract term/duration
- termination_conditions: Key termination provisions
- consideration: Consideration or payment terms
- language: Document language (e.g., "English")
- addresses: List of addresses mentioned
- has_exhibits: "true" or "false" — whether exhibits are referenced
- exhibit_list: List of exhibits referenced

Respond with JSON matching this schema exactly."""


def build_context_block(context: dict) -> str:
    """Format a structured context dict into a text block for the LLM prompt."""
    lines: list[str] = []

    # Named entities by type
    entities = context.get("entities_by_type", {})
    if entities:
        lines.append("NAMED ENTITIES:")
        for etype, names in entities.items():
            if names:
                lines.append(f"  {etype}: {', '.join(names)}")

    # Low-confidence entities with sentence context
    low_conf = context.get("low_confidence_entities", [])
    if low_conf:
        lines.append("")
        lines.append("LOW-CONFIDENCE ENTITIES (need disambiguation):")
        for item in low_conf:
            sent = item.get("sentence", "")
            sent_part = f' — sentence: "{sent}"' if sent else ""
            lines.append(
                f'  "{item["name"]}" ({item.get("type", "unknown")}, '
                f'{item.get("confidence", 0):.2f}){sent_part}'
            )

    # Relationships / SPO triples
    rels = context.get("relationships", [])
    if rels:
        lines.append("")
        lines.append("RELATIONSHIPS:")
        for r in rels[:30]:
            lines.append(f"  {r}")

    # Legal concepts
    concepts = context.get("concepts", [])
    if concepts:
        lines.append("")
        lines.append(f"LEGAL CONCEPTS (top {len(concepts)}):")
        lines.append(f"  {', '.join(concepts)}")

    # Low-confidence concepts
    low_concepts = context.get("low_confidence_concepts", [])
    if low_concepts:
        lines.append("")
        lines.append("LOW-CONFIDENCE CONCEPTS (need disambiguation):")
        for item in low_concepts:
            sent = item.get("sentence", "")
            sent_part = f' — sentence: "{sent}"' if sent else ""
            lines.append(
                f'  "{item["label"]}" ({item.get("confidence", 0):.2f}){sent_part}'
            )

    # Areas of law
    areas = context.get("areas_of_law", [])
    if areas:
        lines.append("")
        lines.append("AREAS OF LAW:")
        for a in areas:
            conf = a.get("confidence", 0)
            pct = conf * 100 if conf <= 1 else conf
            lines.append(f"  {a.get('area', '?')} ({pct:.0f}%)")

    # Properties (OWL ObjectProperties found in text)
    props = context.get("properties", [])
    if props:
        lines.append("")
        lines.append("PROPERTIES/RELATIONS FOUND:")
        for p in props[:20]:
            lines.append(f"  {p}")

    # Document bookends
    header = context.get("header_text", "")
    if header:
        lines.append("")
        lines.append("DOCUMENT HEADER (first ~1000 chars):")
        lines.append(header)

    footer = context.get("footer_text", "")
    if footer:
        lines.append("")
        lines.append("SIGNATURE BLOCK (last ~500 chars):")
        lines.append(footer)

    return "\n".join(lines)


# JSON schema for all 35 LLM-extracted fields
_FIELD_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "case_name": {"type": "string"},
        "court": {"type": "string"},
        "judge": {"type": "string"},
        "case_number": {"type": "string"},
        "parties": {"type": "array", "items": {"type": "string"}},
        "jurisdiction": {"type": "string"},
        "procedural_posture": {"type": "string"},
        "cause_of_action": {"type": "string"},
        "claim_types": {"type": "array", "items": {"type": "string"}},
        "relief_sought": {"type": "string"},
        "disposition": {"type": "string"},
        "standard_of_review": {"type": "string"},
        "governing_law": {"type": "string"},
        "author": {"type": "string"},
        "recipient": {"type": "string"},
        "attorneys": {"type": "array", "items": {"type": "string"}},
        "signatories": {"type": "array", "items": {"type": "string"}},
        "witnesses": {"type": "array", "items": {"type": "string"}},
        "date_filed": {"type": "string"},
        "date_signed": {"type": "string"},
        "date_effective": {"type": "string"},
        "date_due": {"type": "string"},
        "dates_mentioned": {"type": "array", "items": {"type": "string"}},
        "document_title": {"type": "string"},
        "docket_entry_number": {"type": "string"},
        "related_documents": {"type": "array", "items": {"type": "string"}},
        "confidentiality": {"type": "string"},
        "contract_type": {"type": "string"},
        "counterparties": {"type": "array", "items": {"type": "string"}},
        "term_duration": {"type": "string"},
        "termination_conditions": {"type": "string"},
        "consideration": {"type": "string"},
        "language": {"type": "string"},
        "addresses": {"type": "array", "items": {"type": "string"}},
        "has_exhibits": {"type": "string"},
        "exhibit_list": {"type": "array", "items": {"type": "string"}},
    },
}


class MetadataExtractor:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def extract(self, context: dict, doc_type: str) -> dict:
        """Extract metadata from structured pipeline context.

        *context* is a dict built by MetadataStage._build_context() containing
        entities_by_type, relationships, concepts, header/footer text, etc.
        """
        context_block = build_context_block(context)
        prompt = (
            EXTRACT_PROMPT
            .replace("{doc_type}", doc_type)
            .replace("{context_block}", context_block)
        )
        try:
            return await self.llm.structured(prompt, schema=_FIELD_SCHEMA)
        except Exception:
            logger.exception("Metadata extraction failed")
            return {}
