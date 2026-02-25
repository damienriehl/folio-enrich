"""Pipeline stages for OWL Property (verb/relation) extraction.

Split into two stages following the Individual extraction pattern:
- EarlyPropertyStage: Aho-Corasick text matching — runs in parallel with
  EntityRuler + LLMConcept + EarlyIndividual (fast, no LLM dependency)
- LLMPropertyStage: LLM contextual identification + domain/range linking —
  runs after LLMIndividual when resolved class annotations are available
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.llm.base import LLMProvider
from app.services.property.property_deduplicator import deduplicate_properties
from app.services.property.property_matcher import PropertyMatcher

logger = logging.getLogger(__name__)


class EarlyPropertyStage(PipelineStage):
    """Aho-Corasick property matching — fast, no LLM needed.

    Runs in parallel with EntityRuler, LLM Concepts, and EarlyIndividual.
    """

    def __init__(self) -> None:
        self._matcher = PropertyMatcher()

    @property
    def name(self) -> str:
        return "early_property_extraction"

    async def execute(self, job: Job) -> Job:
        from app.config import settings

        if not settings.property_extraction_enabled:
            return job

        if not job.result.canonical_text:
            return job

        full_text = job.result.canonical_text.full_text
        if not full_text:
            return job

        job.status = JobStatus.EXTRACTING_PROPERTIES
        log = job.result.metadata.setdefault("activity_log", [])

        # Build matcher and scan text
        try:
            pattern_count = self._matcher.build()
            raw_properties = self._matcher.match(full_text)
        except Exception:
            logger.warning("Property matching failed", exc_info=True)
            raw_properties = []
            pattern_count = 0

        # Deduplicate overlapping spans
        properties = deduplicate_properties(raw_properties)

        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": f"Property matching: {len(properties)} found ({pattern_count} patterns)",
        })

        job.result.properties = properties

        logger.info(
            "Early property extraction for job %s: %d properties from %d patterns",
            job.id, len(properties), pattern_count,
        )

        return job


class LLMPropertyStage(PipelineStage):
    """LLM property extraction + domain/range cross-linking.

    Runs after LLMIndividual when resolved class annotations are available.
    """

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    @property
    def name(self) -> str:
        return "llm_property_linking"

    async def execute(self, job: Job) -> Job:
        from app.config import settings

        if not settings.property_extraction_enabled:
            return job

        if not job.result.canonical_text:
            return job

        if settings.property_regex_only:
            return job

        if self.llm is None:
            return job

        log = job.result.metadata.setdefault("activity_log", [])
        existing_properties = list(job.result.properties)

        # LLM extraction + class linking
        llm_new = []
        chunks = job.result.canonical_text.chunks
        if chunks:
            try:
                from app.services.property.llm_property_identifier import (
                    LLMPropertyIdentifier,
                )

                identifier = LLMPropertyIdentifier(self.llm)
                llm_new = await identifier.identify_batch(
                    chunks, job.result.annotations, existing_properties
                )
            except Exception:
                logger.warning("LLM property extraction failed", exc_info=True)

        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": f"LLM properties: {len(llm_new)} new",
        })

        # Merge and deduplicate
        combined = existing_properties + llm_new
        deduplicated = deduplicate_properties(combined)

        job.result.properties = deduplicated

        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": (
                f"Property linking complete: {len(deduplicated)} properties "
                f"({len(llm_new)} LLM-discovered, "
                f"{len(existing_properties)} from early extraction)"
            ),
        })

        logger.info(
            "LLM property linking for job %s: %d total properties",
            job.id, len(deduplicated),
        )

        return job
