"""EarlyTripleStage — parallel SVO triple extraction + POS tagging.

Runs in Phase 2 alongside EntityRuler, EarlyIndividual, EarlyProperty.
No dependency on concepts, individuals, or properties.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.models.job import Job
from app.pipeline.stages.base import PipelineStage
from app.services.dependency.parser import DependencyParser


class EarlyTripleStage(PipelineStage):
    """Extract SVO triples and POS tags from all sentences."""

    def __init__(self, parser: DependencyParser | None = None) -> None:
        self.parser = parser or DependencyParser()

    @property
    def name(self) -> str:
        return "early_triple"

    async def execute(self, job: Job) -> Job:
        if not settings.triple_extraction_enabled:
            return job

        if job.result.canonical_text is None:
            return job

        text = job.result.canonical_text.full_text
        if not text or not text.strip():
            return job

        triples, pos_data = self.parser.extract_triples_and_pos(text)

        job.result.triples = triples

        if settings.pos_tagging_enabled:
            job.result.metadata["sentence_pos"] = [
                sp.model_dump() for sp in pos_data
            ]

        log = job.result.metadata.setdefault("activity_log", [])
        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": f"Extracted {len(triples)} SVO triples from {len(pos_data)} sentences",
        })

        return job
