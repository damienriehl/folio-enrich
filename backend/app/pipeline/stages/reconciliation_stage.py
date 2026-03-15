from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.annotation import ConceptMatch
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage, record_lineage
from app.services.reconciliation.reconciler import Reconciler

logger = logging.getLogger(__name__)


# POS tag → multiplier for concept match boost (noun-like tags boost class concepts)
_POS_CONCEPT_BOOST_MULTIPLIERS: dict[str, float] = {
    "NOUN": 1.0,    # base × 1.0 = 0.10
    "PROPN": 1.2,   # base × 1.2 = 0.12
    "ADJ": 0.6,     # base × 0.6 = 0.06
}


class ReconciliationStage(PipelineStage):
    def __init__(self, reconciler: Reconciler | None = None, embedding_service=None) -> None:
        self.reconciler = reconciler or Reconciler(embedding_service=embedding_service)

    @property
    def name(self) -> str:
        return "reconciliation"

    async def execute(self, job: Job) -> Job:
        # Gather ruler concepts
        ruler_raw = job.result.metadata.get("ruler_concepts", [])
        ruler_concepts = [ConceptMatch(**c) for c in ruler_raw]

        # Gather LLM concepts (flatten from per-chunk)
        llm_raw = job.result.metadata.get("llm_concepts", {})
        llm_concepts = [
            ConceptMatch(**c)
            for chunk_concepts in llm_raw.values()
            for c in chunk_concepts
        ]

        # Use embedding triage if embedding service is available
        if self.reconciler._embedding_service is not None:
            results = self.reconciler.reconcile_with_embedding_triage(ruler_concepts, llm_concepts)
        else:
            results = self.reconciler.reconcile(ruler_concepts, llm_concepts)

        # Store reconciled concepts for resolution stage (all start as "preliminary")
        # Propagate _lineage_event from LLM concepts into reconciled dicts
        llm_lineage_by_text: dict[str, dict] = {}
        for chunk_concepts in llm_raw.values():
            for c in chunk_concepts:
                evt = c.get("_lineage_event")
                if evt:
                    llm_lineage_by_text[c.get("concept_text", "").lower()] = evt

        reconciled = []
        for r in results:
            rd: dict = {
                "concept_text": r.concept.concept_text,
                "branches": r.concept.branches,
                "confidence": r.concept.confidence,
                "source": r.concept.source,
                "folio_iri": r.concept.folio_iri,
                "category": r.category,
                "state": "preliminary",
            }
            # Carry forward LLM lineage events
            lineage_events: list[dict] = []
            llm_evt = llm_lineage_by_text.get(r.concept.concept_text.lower())
            if llm_evt:
                lineage_events.append(llm_evt)
            rd["_lineage_events"] = lineage_events
            reconciled.append(rd)
        job.result.metadata["reconciled_concepts"] = reconciled

        # Update preliminary annotation states based on reconciliation results
        reconciled_by_key: dict[tuple[str, str], str] = {}
        for r in results:
            rkey = (r.concept.concept_text.lower(), r.concept.folio_iri or "")
            reconciled_by_key[rkey] = r.category

        _CATEGORY_DETAIL = {
            "both_agree": "Both EntityRuler and LLM agree",
            "conflict_resolved": "Conflict resolved via embedding similarity",
            "ruler_only": "EntityRuler only (confidence >= threshold)",
        }

        # Build secondary text-only lookup for LLM annotations that lack an IRI
        reconciled_by_text: dict[str, str] = {}
        for (text, iri), cat in reconciled_by_key.items():
            if text not in reconciled_by_text:
                reconciled_by_text[text] = cat
            elif cat in ("both_agree", "conflict_resolved"):
                reconciled_by_text[text] = cat  # prefer stronger categories

        for ann in job.result.annotations:
            if ann.state != "preliminary":
                continue
            concept_text = ann.concepts[0].concept_text.lower() if ann.concepts else ""
            concept_iri = ann.concepts[0].folio_iri or "" if ann.concepts else ""
            category = reconciled_by_key.get((concept_text, concept_iri))
            # Fallback: text-only lookup for LLM annotations with empty/different IRI
            if category is None and concept_iri == "":
                category = reconciled_by_text.get(concept_text)
            if category in ("both_agree", "conflict_resolved"):
                ann.state = "confirmed"
                record_lineage(ann, "reconciliation", "confirmed",
                               detail=_CATEGORY_DETAIL.get(category, ""))
            elif category in ("llm_only",):
                # LLM-only concepts stay preliminary (may be confirmed by resolution)
                record_lineage(ann, "reconciliation", "kept",
                               detail="LLM-only concept — awaiting resolution")
            elif category is None:
                # Not in reconciled set — low confidence, filtered out
                ann.state = "rejected"
                record_lineage(ann, "reconciliation", "rejected",
                               detail="Filtered out (not in reconciled set)")
            else:
                # "ruler_only" stays as "preliminary" (confirmed later by resolution)
                record_lineage(ann, "reconciliation", "kept",
                               detail=_CATEGORY_DETAIL.get(category, f"Category: {category}"))

        # POS-based confidence boost + penalty pass
        pos_boosted, pos_penalized = self._apply_pos_adjustments(job)

        # Sync POS-adjusted confidence back to reconciled_concepts metadata dicts
        # so adjustments propagate through Resolution → StringMatch
        self._sync_pos_to_metadata(job)

        confirmed = sum(1 for a in job.result.annotations if a.state == "confirmed")
        ruler_only = sum(1 for r in results if r.category == "ruler_only")
        rejected = sum(1 for a in job.result.annotations if a.state == "rejected")
        log = job.result.metadata.setdefault("activity_log", [])
        msg = f"Reconciled: {confirmed} confirmed, {ruler_only} ruler-only, {rejected} rejected"
        if pos_boosted or pos_penalized:
            msg += f", {pos_boosted} POS-boosted, {pos_penalized} POS-penalized"
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": msg})
        return job

    @staticmethod
    def _apply_pos_adjustments(job: Job) -> tuple[int, int]:
        """Apply POS-based confidence boosts and penalties to annotations."""
        from app.config import settings
        from app.services.nlp.pos_lookup import get_majority_pos

        if not settings.pos_confidence_enabled or not settings.pos_tagging_enabled:
            return 0, 0

        sentence_pos = job.result.metadata.get("sentence_pos", [])
        if not sentence_pos:
            return 0, 0

        penalty = settings.pos_concept_mismatch_penalty
        boost_base = settings.pos_concept_match_boost
        boosted = 0
        penalized = 0

        for ann in job.result.annotations:
            if ann.state == "rejected" or not ann.concepts:
                continue

            concept = ann.concepts[0]
            span_text = ann.span.text

            # Only adjust single-word matches
            if " " in span_text.strip():
                continue

            pos = get_majority_pos(ann.span.start, ann.span.end, sentence_pos)
            if pos is None:
                continue

            # BOOST: POS agrees with class concept (noun-like)
            if pos in _POS_CONCEPT_BOOST_MULTIPLIERS and boost_base > 0:
                boost = boost_base * _POS_CONCEPT_BOOST_MULTIPLIERS[pos]
                concept.confidence = min(1.0, concept.confidence + boost)
                boosted += 1
                record_lineage(
                    ann, "reconciliation", "pos_boosted",
                    detail=f"POS agreement: {pos} for class concept '{concept.concept_text}'",
                    confidence=concept.confidence,
                )

            # PENALTY: POS disagrees with class concept (verb-like) — existing logic
            elif pos in ("VERB", "ADV") and concept.match_type == "alternative":
                concept.confidence = max(0.0, concept.confidence - penalty)
                penalized += 1
                record_lineage(
                    ann, "reconciliation", "pos_penalized",
                    detail=f"POS mismatch: {pos} for noun concept '{concept.concept_text}'",
                    confidence=concept.confidence,
                )
                if concept.confidence < 0.20:
                    ann.state = "rejected"
                    record_lineage(
                        ann, "reconciliation", "rejected",
                        detail="Confidence below 0.20 after POS penalty",
                    )

        return boosted, penalized

    @staticmethod
    def _sync_pos_to_metadata(job: Job) -> None:
        """Sync POS-adjusted confidence from annotations back to reconciled_concepts dicts."""
        reconciled = job.result.metadata.get("reconciled_concepts", [])
        if not reconciled:
            return

        reconciled_by_key: dict[tuple[str, str], dict] = {
            (d["concept_text"].lower(), d.get("folio_iri", "")): d
            for d in reconciled
        }
        for ann in job.result.annotations:
            if not ann.concepts:
                continue
            c = ann.concepts[0]
            key = (c.concept_text.lower(), c.folio_iri or "")
            rd = reconciled_by_key.get(key)
            if rd is not None:
                rd["confidence"] = c.confidence
