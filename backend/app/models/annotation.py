from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class StageEvent(BaseModel):
    stage: str  # "entity_ruler", "reconciliation", "resolution", etc.
    action: str  # "created", "confirmed", "rejected", "enriched", "branch_assigned"
    detail: str = ""
    confidence: float | None = None
    timestamp: str = ""
    reasoning: str = ""


class FeedbackItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    rating: str  # "up" or "down"
    stage: str | None = None  # target a specific stage event, or None for whole annotation
    comment: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Span(BaseModel):
    start: int
    end: int
    text: str
    sentence_text: str | None = None


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
    state: str = "preliminary"  # "preliminary", "confirmed", "rejected", "backup"
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
    dismissed_at: str | None = None  # ISO timestamp when user dismissed
    lineage: list[StageEvent] = Field(default_factory=list)
    feedback: list[FeedbackItem] = Field(default_factory=list)
