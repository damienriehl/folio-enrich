from __future__ import annotations


_CONTEXTUAL_RERANK_TEMPLATE = """You are a legal concept relevance evaluator. Given a document excerpt and a list of candidate FOLIO ontology concepts that were identified in it, score how contextually relevant each concept is to the document.

For each concept, evaluate whether the FOLIO concept truly applies in this document's context — not just whether the text matches a label.

Scoring rubric:
- 0.95 = The concept is unambiguously central to the document's subject matter
- 0.80 = The concept clearly applies in this legal context
- 0.60 = The concept is relevant but secondary or tangential
- 0.40 = The concept is a stretch — the term appears but the FOLIO concept doesn't really fit
- 0.20 = The concept is likely a false positive — the text matches a label but the legal meaning doesn't apply
{document_type_section}
DOCUMENT EXCERPT:
{document_text}

CANDIDATE CONCEPTS:
{concepts_json}

For each concept, respond with JSON:
{"scores": [{"concept_text": "...", "folio_iri": "...", "contextual_score": 0.XX, "reasoning": "brief explanation"}]}"""


def build_contextual_rerank_prompt(
    document_text: str, concepts: list[dict], *, document_type: str = ""
) -> str:
    import json

    concepts_for_prompt = []
    for c in concepts:
        concepts_for_prompt.append({
            "concept_text": c.get("concept_text", ""),
            "folio_iri": c.get("folio_iri", ""),
            "folio_label": c.get("folio_label", ""),
            "folio_definition": (c.get("folio_definition") or "")[:200],
        })

    dt_section = ""
    if document_type:
        dt_section = f"\n## Document Type\nThis document is: {document_type}\n - use that as context when doing your tasks.\n"

    return (
        _CONTEXTUAL_RERANK_TEMPLATE
        .replace("{document_type_section}", dt_section)
        .replace("{document_text}", document_text[:3000])
        .replace("{concepts_json}", json.dumps(concepts_for_prompt, indent=2))
    )
