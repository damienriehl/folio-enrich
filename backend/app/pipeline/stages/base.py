from __future__ import annotations

import abc
from datetime import datetime, timezone

from app.models.annotation import Annotation, StageEvent
from app.models.job import Job


class PipelineStage(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    async def execute(self, job: Job) -> Job:
        """Execute this pipeline stage, mutating the job in place and returning it."""


def record_lineage(
    annotation: Annotation,
    stage: str,
    action: str,
    detail: str = "",
    confidence: float | None = None,
) -> None:
    """Append a StageEvent to an annotation's lineage trail."""
    annotation.lineage.append(
        StageEvent(
            stage=stage,
            action=action,
            detail=detail,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    )
