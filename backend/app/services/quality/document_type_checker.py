"""Post-completion quality cross-check: document type vs. pipeline findings."""

from __future__ import annotations

import logging
from collections import Counter

from app.models.job import Job
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_QUALITY_CHECK_PROMPT = """You are a quality assurance reviewer for a legal document enrichment pipeline.

The document identifies itself as: {self_identified_type}

The pipeline found the following enrichment results:
- Annotation count: {annotation_count}
- Property count: {property_count}
- Top concept branches: {branch_summary}
- Top concept labels: {concept_summary}

Identify any quality concerns:
1. Are there expected concept branches for this document type that are MISSING?
2. Are there unexpected branches that dominate the results?
3. Does the annotation count seem reasonable for this document type?
4. Any other mismatches between the document type and the pipeline findings?

Respond with JSON:
{{"signals": [
  {{"signal": "short description", "severity": "warning or info", "details": "explanation"}}
]}}

If everything looks consistent, return an empty signals array."""


class DocumentTypeChecker:
    """Cross-checks the self-identified document type against pipeline results."""

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def check(self, job: Job) -> list[dict]:
        metadata = job.result.metadata
        self_type = metadata.get("self_identified_type", "")

        if not self_type:
            return []

        # Build summaries of pipeline findings
        resolved = metadata.get("resolved_concepts", [])

        branch_counter: Counter[str] = Counter()
        concept_counter: Counter[str] = Counter()
        for c in resolved:
            branches = c.get("branches", [])
            if branches:
                branch_counter[branches[0]] += 1
            label = c.get("folio_label", c.get("concept_text", ""))
            if label:
                concept_counter[label] += 1

        branch_summary = ", ".join(
            f"{b} (x{n})" for b, n in branch_counter.most_common(10)
        ) or "none"

        concept_summary = ", ".join(
            f"{c} (x{n})" for c, n in concept_counter.most_common(15)
        ) or "none"

        prompt = (
            _QUALITY_CHECK_PROMPT
            .replace("{self_identified_type}", self_type)
            .replace("{annotation_count}", str(len(job.result.annotations)))
            .replace("{property_count}", str(len(job.result.properties)))
            .replace("{branch_summary}", branch_summary)
            .replace("{concept_summary}", concept_summary)
        )

        try:
            result = await self.llm.structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "signals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "signal": {"type": "string"},
                                    "severity": {"type": "string"},
                                    "details": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            )
        except Exception:
            logger.warning("Document type quality check failed", exc_info=True)
            return []

        signals = result.get("signals", [])
        # Normalize severity values
        for s in signals:
            if s.get("severity") not in ("warning", "info"):
                s["severity"] = "info"

        return signals
