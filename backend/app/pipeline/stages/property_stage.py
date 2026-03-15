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

# POS tag → multiplier for property match boost (verb-like tags boost properties)
_POS_PROPERTY_BOOST_MULTIPLIERS: dict[str, float] = {
    "VERB": 1.0,    # base × 1.0 = 0.10
    "AUX": 0.8,     # base × 0.8 = 0.08
}


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
                document_type = job.result.metadata.get("self_identified_type", "")
                llm_new = await identifier.identify_batch(
                    chunks, job.result.annotations, existing_properties,
                    document_type=document_type,
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

        # POS-based boost + penalty for Aho-Corasick property matches
        pos_boosted, pos_penalized = self._apply_pos_adjustments(job, deduplicated)

        job.result.properties = deduplicated

        pos_msg = ""
        if pos_boosted or pos_penalized:
            pos_msg = f", {pos_boosted} POS-boosted, {pos_penalized} POS-penalized"
        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": (
                f"Property linking complete: {len(deduplicated)} properties "
                f"({len(llm_new)} LLM-discovered, "
                f"{len(existing_properties)} from early extraction)"
                + pos_msg
            ),
        })

        logger.info(
            "LLM property linking for job %s: %d total properties",
            job.id, len(deduplicated),
        )

        return job

    @staticmethod
    def _apply_pos_adjustments(job: Job, properties: list) -> tuple[int, int]:
        """Apply POS-based confidence boosts and penalties to properties.

        Handles both single-word and multi-word spans:
        - Single-word: uses majority POS directly
        - Multi-word: priority-based — any VERB/AUX present means verb-like (boost);
          only penalize if all tokens are NOUN/PROPN with no verb presence.
        """
        from app.config import settings
        from app.models.annotation import StageEvent
        from app.services.nlp.pos_lookup import get_majority_pos, get_pos_for_span

        if not settings.pos_confidence_enabled or not settings.pos_tagging_enabled:
            return 0, 0

        sentence_pos = job.result.metadata.get("sentence_pos", [])
        if not sentence_pos:
            return 0, 0

        penalty = settings.pos_property_mismatch_penalty
        boost_base = settings.pos_property_match_boost
        boosted = 0
        penalized = 0

        for prop in properties:
            # Only adjust Aho-Corasick matches, not LLM-sourced
            if prop.source != "aho_corasick":
                continue

            is_multiword = " " in prop.property_text.strip()

            if is_multiword:
                pos_tags = get_pos_for_span(prop.span.start, prop.span.end, sentence_pos)
                if not pos_tags:
                    continue

                has_verb = any(p in ("VERB", "AUX") for p in pos_tags)
                has_noun_only = all(p in ("NOUN", "PROPN", "ADJ", "DET", "ADP") for p in pos_tags)

                if has_verb and boost_base > 0:
                    # Any verb/aux token → boost for property
                    has_aux = any(p == "AUX" for p in pos_tags)
                    mult = _POS_PROPERTY_BOOST_MULTIPLIERS.get("AUX" if has_aux and "VERB" not in pos_tags else "VERB", 1.0)
                    boost = boost_base * mult
                    prop.confidence = min(1.0, prop.confidence + boost)
                    boosted += 1
                    effective_pos = "VERB" if "VERB" in pos_tags else "AUX"
                    prop.lineage.append(StageEvent(
                        stage="llm_property_linking",
                        action="pos_boosted",
                        detail=f"POS agreement: {effective_pos} in multi-word property '{prop.folio_label}'",
                        confidence=prop.confidence,
                    ))
                elif has_noun_only:
                    # All noun-like, no verb → penalize for verb-sense property
                    prop.confidence = max(0.0, prop.confidence - penalty)
                    penalized += 1
                    prop.lineage.append(StageEvent(
                        stage="llm_property_linking",
                        action="pos_penalized",
                        detail=f"POS mismatch: NOUN-dominant multi-word property '{prop.folio_label}'",
                        confidence=prop.confidence,
                    ))
            else:
                pos = get_majority_pos(prop.span.start, prop.span.end, sentence_pos)
                if pos is None:
                    continue

                # BOOST: POS agrees with property (verb-like)
                if pos in _POS_PROPERTY_BOOST_MULTIPLIERS and boost_base > 0:
                    boost = boost_base * _POS_PROPERTY_BOOST_MULTIPLIERS[pos]
                    prop.confidence = min(1.0, prop.confidence + boost)
                    boosted += 1
                    prop.lineage.append(StageEvent(
                        stage="llm_property_linking",
                        action="pos_boosted",
                        detail=f"POS agreement: {pos} for property '{prop.folio_label}'",
                        confidence=prop.confidence,
                    ))

                # PENALTY: NOUN/PROPN for a verb-sense ObjectProperty → penalize
                elif pos in ("NOUN", "PROPN"):
                    prop.confidence = max(0.0, prop.confidence - penalty)
                    penalized += 1
                    prop.lineage.append(StageEvent(
                        stage="llm_property_linking",
                        action="pos_penalized",
                        detail=f"POS mismatch: {pos} for verb-sense property '{prop.folio_label}'",
                        confidence=prop.confidence,
                    ))

        return boosted, penalized
