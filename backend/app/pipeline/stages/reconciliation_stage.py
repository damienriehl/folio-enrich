from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.annotation import ConceptMatch
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage, record_lineage
from app.services.reconciliation.reconciler import Reconciler

logger = logging.getLogger(__name__)


class ReconciliationStage(PipelineStage):
    def __init__(self, reconciler: Reconciler | None = None, embedding_service=None) -> None:
        self.reconciler = reconciler or Reconciler(embedding_service=embedding_service)

    @property
    def name(self) -> str:
        return "reconciliation"

    @staticmethod
    def _get_property_labels() -> set[str]:
        """Get all known property labels (including lemma variants) for filtering."""
        try:
            from app.services.folio.folio_service import FolioService
            svc = FolioService.get_instance()
            labels = set(svc.get_all_property_labels().keys())
            # Also include lemma variants
            from app.services.property.property_matcher import _compute_verb_lemmas
            lemma_map = _compute_verb_lemmas(labels)
            labels.update(lemma_map.keys())
            return labels
        except Exception:
            return set()

    async def execute(self, job: Job) -> Job:
        # Gather ruler concepts
        ruler_raw = job.result.metadata.get("ruler_concepts", [])
        ruler_concepts = [ConceptMatch(**c) for c in ruler_raw]

        # Gather LLM concepts (flatten from per-chunk)
        llm_raw = job.result.metadata.get("llm_concepts", {})
        llm_concepts = []

        # Filter out LLM concepts whose text matches a known property label —
        # these are verbs/relations, not OWL Classes.
        property_labels = self._get_property_labels()

        for chunk_concepts in llm_raw.values():
            for c in chunk_concepts:
                text = c.get("concept_text", "").lower().strip()
                if text in property_labels:
                    logger.debug(
                        "Suppressing LLM concept '%s' — matches property label", text
                    )
                    continue
                llm_concepts.append(ConceptMatch(**c))

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

        for ann in job.result.annotations:
            if ann.state != "preliminary":
                continue
            concept_text = ann.concepts[0].concept_text.lower() if ann.concepts else ""
            concept_iri = ann.concepts[0].folio_iri or "" if ann.concepts else ""
            category = reconciled_by_key.get((concept_text, concept_iri))
            if category in ("both_agree", "conflict_resolved"):
                ann.state = "confirmed"
                record_lineage(ann, "reconciliation", "confirmed",
                               detail=_CATEGORY_DETAIL.get(category, ""))
            elif category is None:
                # Not in reconciled set — low confidence, filtered out
                ann.state = "rejected"
                record_lineage(ann, "reconciliation", "rejected",
                               detail="Filtered out (not in reconciled set)")
            else:
                # "ruler_only" stays as "preliminary" (confirmed later by resolution)
                record_lineage(ann, "reconciliation", "kept",
                               detail=_CATEGORY_DETAIL.get(category, f"Category: {category}"))

        confirmed = sum(1 for a in job.result.annotations if a.state == "confirmed")
        ruler_only = sum(1 for r in results if r.category == "ruler_only")
        rejected = sum(1 for a in job.result.annotations if a.state == "rejected")
        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"Reconciled: {confirmed} confirmed, {ruler_only} ruler-only, {rejected} rejected"})
        return job
