"""Pipeline stages for OWL Individual extraction (three-path hybrid).

Split into two stages for progressive display:
- EarlyIndividualStage: Pass 1 (citations) + Pass 2 (regex/spaCy) — runs in
  parallel with EntityRuler + LLM Concepts (fast, no LLM dependency)
- LLMIndividualStage: Pass 3 (LLM class linking) + Pass 4 (dedup) — runs
  after StringMatch when resolved class annotations are available
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.annotation import Individual
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.folio.folio_service import FolioService
from app.services.individual.citation_extractor import CitationExtractor
from app.services.individual.deduplicator import deduplicate
from app.services.individual.entity_extractors import EntityExtractorRunner
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def _resolve_class_link_iris(
    individuals: list[Individual], folio_svc: FolioService
) -> None:
    """Fill in missing folio_iri on class links using exact label lookup.

    Uses get_all_labels() for case-insensitive exact matching rather than
    search_by_label() which does fuzzy matching and can return wrong concepts
    (e.g. "Caselaw" fuzzy-matching to "Advisory Service").
    """
    all_labels = folio_svc.get_all_labels()
    label_cache: dict[str, tuple[str, str]] = {}  # label → (iri, branch)

    for ind in individuals:
        for link in ind.class_links:
            if link.folio_iri:
                continue  # Already has IRI
            label = link.folio_label
            if not label:
                continue
            if label not in label_cache:
                info = all_labels.get(label.lower())
                if info:
                    label_cache[label] = (info.concept.iri, info.concept.branch)
                else:
                    label_cache[label] = ("", "")
            iri, branch = label_cache[label]
            if iri:
                link.folio_iri = iri
                if not link.branch:
                    link.branch = branch


class EarlyIndividualStage(PipelineStage):
    """Pass 1 (citations) + Pass 2 (regex/spaCy) — fast, no LLM needed.

    Runs in parallel with EntityRuler and LLM Concepts so results appear
    immediately in the UI via SSE.
    """

    def __init__(self) -> None:
        self._citation_extractor = CitationExtractor()
        self._entity_runner = EntityExtractorRunner()

    @property
    def name(self) -> str:
        return "early_individual_extraction"

    async def execute(self, job: Job) -> Job:
        from app.config import settings

        if not settings.individual_extraction_enabled:
            return job

        if not job.result.canonical_text:
            return job

        full_text = job.result.canonical_text.full_text
        if not full_text:
            return job

        job.status = JobStatus.EXTRACTING_INDIVIDUALS
        log = job.result.metadata.setdefault("activity_log", [])

        # Pass 1: Citation extraction (Eyecite + CiteURL)
        try:
            citations = await self._citation_extractor.extract(full_text)
        except Exception:
            logger.warning("Citation extraction failed", exc_info=True)
            citations = []

        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": f"Pass 1 (citations): {len(citations)} found",
        })

        # Pass 2: Custom regex/spaCy extractors
        try:
            entities = await self._entity_runner.extract(full_text)
        except Exception:
            logger.warning("Entity extraction failed", exc_info=True)
            entities = []

        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": f"Pass 2 (regex/spaCy): {len(entities)} found",
        })

        # Store preliminary individuals (pre-dedup for now — LLM stage will dedup)
        all_individuals = citations + entities
        job.result.individuals = deduplicate(all_individuals)

        # Resolve missing IRIs on class links via FOLIO ontology lookup
        try:
            folio_svc = FolioService.get_instance()
            _resolve_class_link_iris(job.result.individuals, folio_svc)
        except Exception:
            logger.warning("Class link IRI resolution failed", exc_info=True)

        logger.info(
            "Early individual extraction for job %s: %d individuals "
            "(%d citations, %d entities)",
            job.id, len(job.result.individuals), len(citations), len(entities),
        )

        return job


class LLMIndividualStage(PipelineStage):
    """Pass 3 (LLM class linking) + Pass 4 (final dedup).

    Runs after StringMatch when resolved class annotations are available.
    Adds LLM-discovered individuals and links existing ones to OWL classes.
    """

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    @property
    def name(self) -> str:
        return "llm_individual_linking"

    async def execute(self, job: Job) -> Job:
        from app.config import settings

        if not settings.individual_extraction_enabled:
            return job

        if not job.result.canonical_text:
            return job

        if settings.individual_regex_only:
            return job

        if self.llm is None:
            return job

        log = job.result.metadata.setdefault("activity_log", [])
        existing_individuals = list(job.result.individuals)

        # Pass 3: LLM extraction + class linking
        llm_new = []
        chunks = job.result.canonical_text.chunks
        if chunks:
            try:
                from app.services.individual.llm_individual_identifier import (
                    LLMIndividualIdentifier,
                )

                identifier = LLMIndividualIdentifier(self.llm)
                document_type = job.result.metadata.get("self_identified_type", "")
                llm_new = await identifier.identify_batch(
                    chunks, job.result.annotations, existing_individuals,
                    document_type=document_type,
                )
            except Exception:
                logger.warning("LLM individual extraction failed", exc_info=True)

        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": f"Pass 3 (LLM): {len(llm_new)} new individuals",
        })

        # Pass 4: Final merge & deduplicate (early individuals + LLM individuals)
        combined = existing_individuals + llm_new
        deduplicated = deduplicate(combined)

        job.result.individuals = deduplicated

        # Resolve missing IRIs on class links via FOLIO ontology lookup
        try:
            folio_svc = FolioService.get_instance()
            _resolve_class_link_iris(job.result.individuals, folio_svc)
        except Exception:
            logger.warning("Class link IRI resolution failed", exc_info=True)

        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": (
                f"Individual linking complete: {len(deduplicated)} individuals "
                f"({len(llm_new)} LLM-discovered, "
                f"{len(existing_individuals)} from early extraction)"
            ),
        })

        logger.info(
            "LLM individual linking for job %s: %d total individuals",
            job.id, len(deduplicated),
        )

        return job


# Backward-compatible alias — tests may reference this
IndividualExtractionStage = EarlyIndividualStage
