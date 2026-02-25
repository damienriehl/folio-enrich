from __future__ import annotations

import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.annotation import Annotation, Individual, PropertyAnnotation
from app.models.document import CanonicalText, DocumentInput


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    NORMALIZING = "normalizing"
    ENRICHING = "enriching"
    IDENTIFYING = "identifying"
    RESOLVING = "resolving"
    MATCHING = "matching"
    JUDGING = "judging"
    EXTRACTING_INDIVIDUALS = "extracting_individuals"
    EXTRACTING_PROPERTIES = "extracting_properties"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResult(BaseModel):
    canonical_text: CanonicalText | None = None
    annotations: list[Annotation] = Field(default_factory=list)
    individuals: list[Individual] = Field(default_factory=list)
    properties: list[PropertyAnnotation] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class Job(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input: DocumentInput | None = None
    result: JobResult = Field(default_factory=JobResult)
    error: str | None = None
