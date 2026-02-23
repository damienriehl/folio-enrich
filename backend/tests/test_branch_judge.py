from __future__ import annotations

from typing import Any

import pytest

from app.services.concept.branch_judge import BranchJudge
from app.services.llm.base import LLMProvider


class FakeBranchLLM(LLMProvider):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        return {"branch": "Legal Processes", "confidence": 0.92, "reasoning": "test"}

    async def test_connection(self) -> bool:
        return True

    async def list_models(self):
        return []


class TestBranchJudge:
    @pytest.mark.asyncio
    async def test_judge_returns_branch(self):
        judge = BranchJudge(FakeBranchLLM())
        result = await judge.judge(
            "motion to dismiss",
            "The defendant filed a motion to dismiss.",
            ["Legal Processes", "Legal Concepts"],
        )
        assert result["branch"] == "Legal Processes"
        assert result["confidence"] == 0.92

    @pytest.mark.asyncio
    async def test_judge_batch(self):
        judge = BranchJudge(FakeBranchLLM())
        results = await judge.judge_batch([
            {
                "concept_text": "motion",
                "sentence": "The motion was filed.",
                "candidate_branches": ["Legal Processes"],
            },
            {
                "concept_text": "court",
                "sentence": "The court ruled.",
                "candidate_branches": ["Legal Entities"],
            },
        ])
        assert len(results) == 2
        assert all(r["branch"] == "Legal Processes" for r in results)
