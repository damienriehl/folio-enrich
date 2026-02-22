from __future__ import annotations

from typing import Any

import pytest

from app.services.llm.base import LLMProvider
from app.services.testing.synthetic_generator import DOC_TYPES, SyntheticGenerator


class FakeSyntheticLLM(LLMProvider):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return "IN THE UNITED STATES DISTRICT COURT\nFOR THE SOUTHERN DISTRICT OF NEW YORK\n\nCase No. 1:24-cv-00001\n\nPlaintiff v. Defendant\n\nMOTION TO DISMISS"

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        return {}


class TestSyntheticGenerator:
    @pytest.mark.asyncio
    async def test_generate(self):
        generator = SyntheticGenerator(FakeSyntheticLLM())
        text = await generator.generate("Motion to Dismiss", "medium", "Federal")
        assert "DISTRICT COURT" in text
        assert len(text) > 50

    def test_list_doc_types(self):
        types = SyntheticGenerator.list_doc_types()
        assert "Litigation" in types
        assert "Contracts" in types
        assert len(types) == 9
        assert "Motion to Dismiss" in types["Litigation"]
