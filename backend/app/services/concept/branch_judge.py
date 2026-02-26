from __future__ import annotations

import logging
from typing import Any

from app.services.llm.base import LLMProvider
from app.services.llm.prompts.templates import get_branch_detail

logger = logging.getLogger(__name__)

_BRANCH_JUDGE_TEMPLATE = """You are a legal ontology expert. Given a concept that appears in a sentence, determine which FOLIO ontology branch it **best** belongs to.

FOLIO branches:
{branch_info}
{document_type_section}
Given:
- **concept**: {concept_text}
- **sentence**: {sentence}
- **candidate_branches**: {candidates}
{folio_context}
Pick the SINGLE best branch. Respond with JSON:
{{"branch": "...", "confidence": 0.95, "reasoning": "..."}}"""


def _build_folio_context(concept_text: str, candidate_branches: list[str]) -> str:
    """Look up FOLIO concepts matching the concept text and format context for the LLM."""
    try:
        from app.services.folio.folio_service import FolioService
        folio = FolioService.get_instance()
        results = folio.search_by_label(concept_text, top_k=10)
    except Exception:
        return ""

    if not results:
        return ""

    # Filter to concepts in candidate branches
    relevant = []
    for fc, score in results:
        if fc.branch in candidate_branches:
            relevant.append(fc)

    if not relevant:
        return ""

    lines = [f'\nPossible FOLIO concepts for "{concept_text}":']
    for fc in relevant[:5]:
        entry = f'- "{fc.preferred_label}" [{fc.branch}]'
        if fc.definition:
            entry += f" — {fc.definition[:100]}"
        if fc.examples:
            entry += f" (e.g., {', '.join(fc.examples[:2])})"
        lines.append(entry)

    return "\n".join(lines) + "\n"


class BranchJudge:
    def __init__(self, llm: LLMProvider, folio_service=None) -> None:
        self.llm = llm
        self._folio_service = folio_service

    async def judge(
        self,
        concept_text: str,
        sentence: str,
        candidate_branches: list[str],
        *,
        document_type: str = "",
    ) -> dict:
        folio_context = _build_folio_context(concept_text, candidate_branches)
        branch_info = get_branch_detail()

        dt_section = ""
        if document_type:
            dt_section = f"\n## Document Type\nThis document is: {document_type}\n - use that as context when doing your tasks.\n"

        prompt = (
            _BRANCH_JUDGE_TEMPLATE
            .replace("{branch_info}", branch_info)
            .replace("{document_type_section}", dt_section)
            .replace("{concept_text}", concept_text)
            .replace("{sentence}", sentence)
            .replace("{candidates}", ", ".join(candidate_branches))
            .replace("{folio_context}", folio_context)
        )

        try:
            result = await self.llm.structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "branch": {"type": "string"},
                        "confidence": {"type": "number"},
                        "reasoning": {"type": "string"},
                    },
                },
            )
            return result
        except Exception:
            logger.exception("Branch Judge failed for concept: %s", concept_text)
            return {
                "branch": candidate_branches[0] if candidate_branches else "",
                "confidence": 0.5,
                "reasoning": "fallback",
            }

    async def judge_batch(
        self, items: list[dict], *, document_type: str = ""
    ) -> list[dict]:
        import asyncio

        tasks = [
            self.judge(
                item["concept_text"],
                item["sentence"],
                item.get("candidate_branches", []),
                document_type=document_type,
            )
            for item in items
        ]
        return await asyncio.gather(*tasks, return_exceptions=False)
