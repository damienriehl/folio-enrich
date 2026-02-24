from __future__ import annotations

from pydantic import BaseModel, Field


class FeedbackEntry(BaseModel):
    """Self-contained feedback record: user opinion + system lineage snapshot.

    Persists across job cleanup so feedback and the system's reasoning are
    available until the user explicitly exports or clears them.
    """

    id: str
    job_id: str
    annotation_id: str
    rating: str  # "up" or "down"
    stage: str | None = None
    comment: str = ""
    # Concept context (self-contained even after job is deleted)
    annotation_text: str = ""
    folio_iri: str | None = None
    folio_label: str | None = None
    # System lineage snapshot — captured at feedback time
    lineage: list[dict] = Field(default_factory=list)
    created_at: str = ""


class InsightsSummary(BaseModel):
    """Aggregated feedback insights."""

    total_feedback: int = 0
    thumbs_up: int = 0
    thumbs_down: int = 0
    by_stage: dict[str, dict[str, int]] = {}  # {"entity_ruler": {"up": 5, "down": 2}}
    most_downvoted_concepts: list[dict] = []
    recent_feedback: list[FeedbackEntry] = []
