from __future__ import annotations

import logging
from collections import Counter

from app.models.job import Job
from app.services.llm.base import LLMProvider
from app.services.llm.prompts.area_of_law import build_area_of_law_prompt

logger = logging.getLogger(__name__)


class AreaOfLawAssessor:
    """Classifies a document's areas of law based on pipeline results."""

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def assess(self, job: Job) -> list[dict]:
        metadata = job.result.metadata

        # Gather inputs
        document_type = metadata.get("document_type", "Unknown")
        extracted_fields = metadata.get("extracted_fields", {})

        # Build concepts summary: deduplicated by label+branch with counts
        resolved = metadata.get("resolved_concepts", [])
        counter: Counter[str] = Counter()
        for c in resolved:
            branches = c.get('branches', [])
            branch_str = branches[0] if branches else ''
            key = f"{c.get('folio_label', c.get('concept_text', ''))} [{branch_str}]"
            counter[key] += 1

        top_concepts = counter.most_common(30)
        concepts_summary = ", ".join(
            f"{label} (x{count})" if count > 1 else label
            for label, count in top_concepts
        ) or "No concepts extracted"

        prompt = build_area_of_law_prompt(
            document_type=document_type,
            extracted_fields=extracted_fields,
            concepts_summary=concepts_summary,
        )

        result = await self.llm.structured(
            prompt,
            schema={
                "type": "object",
                "properties": {
                    "areas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "area": {"type": "string"},
                                "confidence": {"type": "number"},
                                "reasoning": {"type": "string"},
                            },
                        },
                    },
                },
            },
        )

        areas = result.get("areas", [])
        # Filter to confidence >= 0.5 and sort descending
        areas = [a for a in areas if a.get("confidence", 0) >= 0.5]
        areas.sort(key=lambda a: a.get("confidence", 0), reverse=True)
        return areas
