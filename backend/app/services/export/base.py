from __future__ import annotations

import abc

from app.models.job import Job


class ExporterBase(abc.ABC):
    @property
    @abc.abstractmethod
    def format_name(self) -> str: ...

    @property
    @abc.abstractmethod
    def content_type(self) -> str: ...

    @abc.abstractmethod
    def export(self, job: Job) -> str | bytes:
        """Export job results to the target format."""
