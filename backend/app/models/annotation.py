from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class Span(BaseModel):
    start: int
    end: int
    text: str


class ConceptMatch(BaseModel):
    concept_text: str
    folio_iri: str | None = None
    folio_label: str | None = None
    folio_definition: str | None = None
    branches: list[str] = Field(default_factory=list)
    branch_color: str | None = None
    confidence: float = 0.0
    source: str = "llm"  # "llm", "entity_ruler", "semantic_ruler", "reconciled"
    match_type: str | None = None  # "preferred" or "alternative" (from EntityRuler)
    state: str = "preliminary"  # "preliminary", "confirmed", "rejected"
    hierarchy_path: list[str] | None = None
    iri_hash: str | None = None
    children_count: int | None = None
    translations: dict[str, str] | None = None
    folio_examples: list[str] | None = None
    folio_notes: list[str] | None = None
    folio_see_also: list[str] | None = None
    folio_source: str | None = None
    folio_alt_labels: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_branch(cls, data):
        if isinstance(data, dict) and "branch" in data and "branches" not in data:
            b = data.pop("branch")
            data["branches"] = [b] if b else []
        return data


class Annotation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    span: Span
    concepts: list[ConceptMatch] = Field(default_factory=list)
    state: str = "preliminary"  # "preliminary", "confirmed", "rejected"
