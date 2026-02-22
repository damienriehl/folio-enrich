from __future__ import annotations

import logging

from app.models.annotation import ConceptMatch
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.entity_ruler.ruler import FOLIOEntityRuler
from app.services.folio.folio_service import FolioService

logger = logging.getLogger(__name__)


class EntityRulerStage(PipelineStage):
    def __init__(self, ruler: FOLIOEntityRuler | None = None) -> None:
        self.ruler = ruler or FOLIOEntityRuler()
        self._patterns_loaded = False

    def _ensure_patterns_loaded(self) -> None:
        """Load FOLIO patterns into the EntityRuler on first use."""
        if self._patterns_loaded:
            return
        try:
            folio_service = FolioService.get_instance()
            all_labels = folio_service.get_all_labels()
            if all_labels:
                self.ruler.load_patterns(all_labels)
                logger.info("EntityRuler loaded %d FOLIO patterns", len(all_labels))
            else:
                logger.warning("No FOLIO labels found — EntityRuler will be empty")
        except Exception:
            logger.warning("Failed to load FOLIO patterns into EntityRuler", exc_info=True)
        self._patterns_loaded = True

    @property
    def name(self) -> str:
        return "entity_ruler"

    async def execute(self, job: Job) -> Job:
        if job.result.canonical_text is None:
            return job

        self._ensure_patterns_loaded()
        matches = self.ruler.find_matches(job.result.canonical_text.full_text)

        ruler_concepts = []
        for match in matches:
            ruler_concepts.append(
                ConceptMatch(
                    concept_text=match.text,
                    folio_iri=match.entity_id,
                    confidence=1.0,  # Deterministic match
                    source="entity_ruler",
                ).model_dump()
            )

        job.result.metadata["ruler_concepts"] = ruler_concepts
        logger.info("EntityRuler found %d matches for job %s", len(ruler_concepts), job.id)
        return job
