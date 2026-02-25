"""LLM prompt template for OWL Property (verb/relation) extraction."""

from __future__ import annotations

_PROPERTY_EXTRACTION_TEMPLATE = """You are a legal verb/relation extractor and OWL ObjectProperty linker. Given a chunk of legal text along with:
1. The OWL class annotations already identified in this chunk
2. Properties (verbs/relations) already found by automated text matching

Your job is TWO-FOLD:
A. Extract any ADDITIONAL legal verbs/relations that the automated matchers missed
B. Identify domain/range CLASS links for each property (what the verb connects)

## What is an OWL ObjectProperty?
A property is a VERB or RELATION that connects concepts. Examples:
- "reversed" — the court REVERSED the lower court's decision
- "remanded" — the case was REMANDED for further proceedings
- "drafted" — the attorney DRAFTED the motion
- "affirmed" — the appellate court AFFIRMED the ruling
- "denied" — the court DENIED the motion
- "granted" — summary judgment was GRANTED
- "filed" — the complaint was FILED in district court
- "argued" — counsel ARGUED that the statute applied

## What is NOT a property?
- Nouns: "summary judgment", "court", "plaintiff" — these are OWL Classes
- Named entities: "John Smith", "42 U.S.C. § 1983" — these are OWL Individuals
- Common verbs without legal significance: "is", "was", "has", "had", "the"

## OWL Class Annotations in this chunk:
{class_annotations}

## Properties already found by automated matching:
{existing_properties}

## FOLIO Property Labels (for reference):
{property_labels}

## Instructions:
1. For each EXISTING property above, identify which OWL class annotations serve as the subject (domain) and object (range) of the verb.
2. Identify any ADDITIONAL legal verbs/relations that the automated matchers missed. Focus on:
   - Court actions: reversed, remanded, affirmed, denied, granted, dismissed, vacated, overruled
   - Party actions: filed, argued, moved, appealed, objected, stipulated, alleged
   - Document actions: drafted, executed, signed, amended, ratified, recorded
   - Any other legally significant verbs that link concepts together

## Confidence calibration:
- 0.95 = unambiguous legal verb with clear FOLIO property match and identified domain/range
- 0.75 = likely property match but domain/range uncertain
- 0.55 = plausible legal verb but no clear FOLIO property match
- 0.35 = weak signal, speculative

Respond with JSON:
{{"properties": [
  {{
    "property_text": "exact verb text from document",
    "folio_label": "matching FOLIO property label (if any)",
    "domain_annotation_ids": ["id1"],
    "range_annotation_ids": ["id2"],
    "confidence": 0.85,
    "is_new": true
  }}
]}}

- Set "is_new": false for existing properties you're enriching with domain/range links
- Set "is_new": true for new properties you discovered
- "domain_annotation_ids" and "range_annotation_ids" reference annotation IDs from the class list above

TEXT:
{text}"""


def build_property_extraction_prompt(
    text: str,
    class_annotations: list[dict],
    existing_properties: list[dict],
    property_labels: list[str],
) -> str:
    """Build the LLM prompt for property extraction."""
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

    # Format existing properties
    if existing_properties:
        prop_lines = []
        for prop in existing_properties:
            text_ = prop.get("property_text", "?")
            label = prop.get("folio_label", "?")
            source = prop.get("source", "?")
            prop_lines.append(f'- "{text_}" → {label} (source: {source})')
        prop_str = "\n".join(prop_lines)
    else:
        prop_str = "(none found by automated matchers in this chunk)"

    # Format available property labels (sample for context)
    labels_str = ", ".join(property_labels[:50]) if property_labels else "(none available)"

    return (
        _PROPERTY_EXTRACTION_TEMPLATE
        .replace("{class_annotations}", ann_str)
        .replace("{existing_properties}", prop_str)
        .replace("{property_labels}", labels_str)
        .replace("{text}", text)
    )
