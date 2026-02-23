from __future__ import annotations

import logging

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.entity_ruler.ruler import EntityRulerMatch, FOLIOEntityRuler
from app.services.entity_ruler.semantic_ruler import SemanticEntityRuler
from app.services.folio.folio_service import FolioService

logger = logging.getLogger(__name__)

# Confidence scores based on match quality
# Multi-word preferred labels are almost certainly correct
# Single-word alt labels (e.g., "grant" → Donation) are very unreliable
_CONFIDENCE = {
    ("preferred", True): 0.95,   # multi-word preferred label
    ("preferred", False): 0.80,  # single-word preferred label
    ("alternative", True): 0.65, # multi-word alternative label
    ("alternative", False): 0.35,  # single-word alternative label — high false-positive rate
}


def _match_confidence(match: EntityRulerMatch) -> float:
    """Compute confidence score based on match type and word count."""
    is_multi_word = len(match.text.split()) > 1
    return _CONFIDENCE.get((match.match_type, is_multi_word), 0.50)


class EntityRulerStage(PipelineStage):
    def __init__(self, ruler: FOLIOEntityRuler | None = None, embedding_service=None) -> None:
        self.ruler = ruler or FOLIOEntityRuler()
        self._embedding_service = embedding_service
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
        full_text = job.result.canonical_text.full_text
        matches = self.ruler.find_matches(full_text)

        ruler_concepts = []
        for match in matches:
            confidence = _match_confidence(match)
            ruler_concepts.append(
                ConceptMatch(
                    concept_text=match.text,
                    folio_iri=match.entity_id,
                    confidence=confidence,
                    source="entity_ruler",
                    match_type=match.match_type,
                ).model_dump()
            )

        # Store match_type metadata separately for reconciliation
        match_types = {}
        for match in matches:
            match_types[match.text.lower()] = {
                "match_type": match.match_type,
                "is_multi_word": len(match.text.split()) > 1,
                "confidence": _match_confidence(match),
                "folio_iri": match.entity_id,
            }

        # Semantic EntityRuler: find near-matches missed by exact matching
        semantic_matches = []
        if self._embedding_service is not None and self._embedding_service.index_size > 0:
            known_spans = {(m.start_char, m.end_char) for m in matches}
            semantic_ruler = SemanticEntityRuler(self._embedding_service)
            semantic_matches = semantic_ruler.find_semantic_matches(full_text, known_spans)
            for sm in semantic_matches:
                ruler_concepts.append(
                    ConceptMatch(
                        concept_text=sm.text,
                        folio_iri=sm.iri,
                        folio_label=sm.matched_label,
                        confidence=sm.similarity,
                        source="semantic_ruler",
                    ).model_dump()
                )
            if semantic_matches:
                logger.info(
                    "SemanticEntityRuler found %d additional matches for job %s",
                    len(semantic_matches), job.id,
                )

        job.result.metadata["ruler_concepts"] = ruler_concepts
        job.result.metadata["ruler_match_types"] = match_types

        # Create preliminary annotations from matches for progressive rendering
        preliminary_annotations = self._build_preliminary_annotations(
            matches, full_text
        )
        # Add semantic match annotations (reuse results from above)
        for sm in semantic_matches:
            preliminary_annotations.append(
                Annotation(
                    span=Span(start=sm.start, end=sm.end, text=sm.text),
                    concepts=[ConceptMatch(
                        concept_text=sm.text,
                        folio_iri=sm.iri,
                        folio_label=sm.matched_label,
                        confidence=sm.similarity,
                        source="semantic_ruler",
                    )],
                    state="preliminary",
                )
            )

        # Resolve overlapping spans (prefer longer matches)
        preliminary_annotations.sort(key=lambda a: (a.span.start, -(a.span.end - a.span.start)))
        deduped: list[Annotation] = []
        last_end = -1
        for ann in preliminary_annotations:
            if ann.span.start >= last_end:
                deduped.append(ann)
                last_end = ann.span.end

        job.result.annotations = deduped

        # Activity log
        from datetime import datetime, timezone
        preferred = sum(1 for m in matches if m.match_type == "preferred")
        alternative = len(matches) - preferred
        msg = f"Found {len(ruler_concepts)} matches ({preferred} preferred, {alternative} alternative)"
        if semantic_matches:
            msg += f" + {len(semantic_matches)} semantic"
        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": msg})

        logger.info("EntityRuler found %d total matches for job %s", len(ruler_concepts), job.id)
        return job

    def _build_preliminary_annotations(
        self, matches: list[EntityRulerMatch], full_text: str
    ) -> list[Annotation]:
        """Build preliminary Annotation objects from EntityRuler matches."""
        annotations: list[Annotation] = []
        for match in matches:
            confidence = _match_confidence(match)
            annotations.append(
                Annotation(
                    span=Span(
                        start=match.start_char,
                        end=match.end_char,
                        text=full_text[match.start_char:match.end_char],
                    ),
                    concepts=[ConceptMatch(
                        concept_text=match.text,
                        folio_iri=match.entity_id,
                        confidence=confidence,
                        source="entity_ruler",
                        match_type=match.match_type,
                    )],
                    state="preliminary",
                )
            )
        return annotations
