from __future__ import annotations

from pydantic import BaseModel, Field


class Span(BaseModel):
    start: int
    end: int
    text: str


class ConceptMatch(BaseModel):
    concept_text: str
    folio_iri: str | None = None
    folio_label: str | None = None
    folio_definition: str | None = None
    branch: str | None = None
    confidence: float = 0.0
    source: str = "llm"  # "llm", "entity_ruler", "semantic_ruler", "reconciled"
    match_type: str | None = None  # "preferred" or "alternative" (from EntityRuler)
    state: str = "preliminary"  # "preliminary", "confirmed", "rejected"


class Annotation(BaseModel):
    span: Span
    concepts: list[ConceptMatch] = Field(default_factory=list)
