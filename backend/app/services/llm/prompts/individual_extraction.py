"""LLM prompt template for OWL Individual extraction (Pass 3)."""

from __future__ import annotations

_INDIVIDUAL_EXTRACTION_TEMPLATE = """You are a legal named entity extractor and OWL class linker. Given a chunk of legal text along with:
1. The OWL class annotations already identified in this chunk
2. Named entities already found by automated extractors

Your job is TWO-FOLD:
A. Extract any ADDITIONAL named individuals that the automated extractors missed
B. LINK all individuals (both existing and new) to the correct OWL class annotations

## What is an OWL Individual?
An individual is a SPECIFIC, NAMED instance of an OWL class. Examples:
- "John Smith" is an individual instance of the class "Plaintiff" or "Person"
- "42 U.S.C. § 1983" is an individual instance of the class "Statute"
- "Smith v. Jones, 123 U.S. 456 (1987)" is an individual instance of the class "Caselaw"
- "Google LLC" is an individual instance of the class "Organization"
- "the May 2024 Purchase Agreement" is an individual instance of "Contract"
- "$500,000" is an individual instance of "Monetary Amount"
- "December 15, 2023" is an individual instance of "Date"

## What is NOT an individual?
- Generic references: "the plaintiff", "a court", "the statute" — these refer to classes, not instances
- Abstract concepts: "negligence", "breach of contract" — these ARE the OWL classes themselves
- Pronouns: "he", "they", "it"

## OWL Class Annotations in this chunk:
{class_annotations}

## Individuals already found by automated extractors:
{existing_individuals}

## Instructions:
1. For each EXISTING individual above, determine which OWL class annotation(s) it should be linked to. Use the annotation_id from the class annotations list.
2. Identify any ADDITIONAL specific named entities the extractors missed. Focus on:
   - Specific documents referenced by name ("the Employment Agreement dated March 1, 2024")
   - Named events ("the December 2023 closing")
   - Role-specific identifications (the LLM knows "John Smith" is specifically the Plaintiff)
   - Non-U.S. or unusual citation formats
   - Any other specific named instances of the OWL classes listed above

## Confidence calibration:
- 0.95 = unambiguous named entity with clear class link (e.g., explicit "Plaintiff John Smith")
- 0.70 = likely entity/link but some ambiguity (e.g., "Smith" could be plaintiff or witness)
- 0.50 = plausible but uncertain (e.g., "the agreement" — might refer to a specific document)
- 0.30 = weak signal, speculative link

Respond with JSON:
{{"individuals": [
  {{
    "name": "canonical name",
    "mention_text": "exact text from document",
    "individual_type": "named_entity or legal_citation",
    "class_annotation_ids": ["id1", "id2"],
    "class_labels": ["Plaintiff", "Person"],
    "confidence": 0.85,
    "is_new": true
  }}
]}}

- Set "is_new": false for existing individuals you're linking to classes
- Set "is_new": true for new individuals you discovered
- "class_annotation_ids" should reference the annotation IDs from the class list above (when available)
- "class_labels" should list the FOLIO class labels this individual instantiates

TEXT:
{text}"""


def build_individual_extraction_prompt(
    text: str,
    class_annotations: list[dict],
    existing_individuals: list[dict],
) -> str:
    """Build the LLM prompt for individual extraction."""
    # Format class annotations
    if class_annotations:
        ann_lines = []
        for ann in class_annotations:
            ann_id = ann.get("id", "?")
            label = ann.get("label", "?")
            span_text = ann.get("span_text", "?")
            branch = ann.get("branch", "")
            ann_lines.append(f'- [{ann_id}] "{span_text}" → {label} (branch: {branch})')
        ann_str = "\n".join(ann_lines)
    else:
        ann_str = "(none found in this chunk)"

    # Format existing individuals
    if existing_individuals:
        ind_lines = []
        for ind in existing_individuals:
            name = ind.get("name", "?")
            itype = ind.get("type", "named_entity")
            source = ind.get("source", "?")
            ind_lines.append(f'- "{name}" (type: {itype}, source: {source})')
        ind_str = "\n".join(ind_lines)
    else:
        ind_str = "(none found by automated extractors in this chunk)"

    return (
        _INDIVIDUAL_EXTRACTION_TEMPLATE
        .replace("{class_annotations}", ann_str)
        .replace("{existing_individuals}", ind_str)
        .replace("{text}", text)
    )
