from __future__ import annotations

import abc

from app.models.job import Job


class PipelineStage(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    async def execute(self, job: Job) -> Job:
        """Execute this pipeline stage, mutating the job in place and returning it."""
