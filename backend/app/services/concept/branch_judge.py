from __future__ import annotations

import logging
from typing import Any

from app.services.llm.base import LLMProvider
from app.services.llm.prompts.templates import BRANCH_LIST

logger = logging.getLogger(__name__)

BRANCH_JUDGE_PROMPT = f"""You are a legal ontology expert. Given a concept that appears in a sentence, determine which FOLIO ontology branch it **best** belongs to.

FOLIO branches:
{BRANCH_LIST}

Given:
- **concept**: {{concept_text}}
- **sentence**: {{sentence}}
- **candidate_branches**: {{candidates}}

Pick the SINGLE best branch. Respond with JSON:
{{"branch": "...", "confidence": 0.95, "reasoning": "..."}}"""


class BranchJudge:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def judge(
        self,
        concept_text: str,
        sentence: str,
        candidate_branches: list[str],
    ) -> dict:
        prompt = BRANCH_JUDGE_PROMPT.replace("{concept_text}", concept_text)
        prompt = prompt.replace("{sentence}", sentence)
        prompt = prompt.replace("{candidates}", ", ".join(candidate_branches))

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
        self, items: list[dict]
    ) -> list[dict]:
        import asyncio

        tasks = [
            self.judge(
                item["concept_text"],
                item["sentence"],
                item.get("candidate_branches", []),
            )
            for item in items
        ]
        return await asyncio.gather(*tasks, return_exceptions=False)
