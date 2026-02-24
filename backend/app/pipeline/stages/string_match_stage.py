from __future__ import annotations

from datetime import datetime, timezone

from app.models.annotation import Annotation, ConceptMatch, Span, StageEvent
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage, record_lineage
from app.services.matching.aho_corasick import AhoCorasickMatcher
from app.services.normalization.normalizer import build_sentence_index, find_sentence_for_span


_ALT_LABEL_STOPWORDS: frozenset[str] = frozenset({
    "act", "bar", "bill", "bond", "brief", "case", "charge", "claim",
    "code", "count", "court", "deed", "due", "duty", "fee", "fine",
    "firm", "fund", "grant", "hold", "law", "lien", "loan", "loss",
    "note", "order", "party", "pay", "plea", "right", "rule", "sale",
    "seal", "suit", "tax", "term", "title", "tort", "trust", "use",
    "wage", "ward", "will", "writ",
})


class StringMatchStage(PipelineStage):
    @property
    def name(self) -> str:
        return "string_matching"

    @staticmethod
    def _is_safe_alt_label(label: str) -> bool:
        """Check if an alt label is safe to add to the automaton (not a common false positive)."""
        if len(label) <= 3:
            return False
        # Single-word labels that are common English words should be skipped
        if " " not in label and label.lower() in _ALT_LABEL_STOPWORDS:
            return False
        return True

    async def execute(self, job: Job) -> Job:
        job.status = JobStatus.MATCHING
        if job.result.canonical_text is None:
            return job

        resolved_concepts = job.result.metadata.get("resolved_concepts", [])
        if not resolved_concepts:
            return job

        # Build Aho-Corasick automaton from resolved concept texts
        matcher = AhoCorasickMatcher()
        # Deduplicate by concept text
        concept_map: dict[str, dict] = {}
        for rc in resolved_concepts:
            key = rc["concept_text"].lower()
            if key not in concept_map or rc["confidence"] > concept_map[key]["confidence"]:
                concept_map[key] = rc

            # Also add alt labels and hidden label as patterns pointing to same data
            alt_labels = rc.get("folio_alt_labels") or []
            for alt in alt_labels:
                alt_key = alt.lower()
                if alt_key not in concept_map and self._is_safe_alt_label(alt):
                    concept_map[alt_key] = rc

            hidden = rc.get("folio_hidden_label") or ""
            if hidden:
                hidden_key = hidden.lower()
                if hidden_key not in concept_map and self._is_safe_alt_label(hidden):
                    concept_map[hidden_key] = rc

        for text, data in concept_map.items():
            matcher.add_pattern(text, data)
        matcher.build()

        # Search full canonical text
        full_text = job.result.canonical_text.full_text
        sentence_index = build_sentence_index(full_text)
        matches = matcher.search(full_text)

        # Build lookup of existing annotations by span for merging
        existing_by_span: dict[tuple[int, int], Annotation] = {}
        for ann in job.result.annotations:
            existing_by_span[(ann.span.start, ann.span.end)] = ann

        # Merge Aho-Corasick matches with existing annotations
        new_annotations: list[Annotation] = []
        seen_spans: set[tuple[int, int]] = set()

        for match in matches:
            span_key = (match.start, match.end)
            seen_spans.add(span_key)
            concept = ConceptMatch(
                concept_text=match.value.get("concept_text", match.pattern),
                folio_iri=match.value.get("folio_iri"),
                folio_label=match.value.get("folio_label"),
                folio_definition=match.value.get("folio_definition"),
                branches=match.value.get("branches", []),
                confidence=match.value.get("confidence", 0.0),
                source=match.value.get("source", "matched"),
                state="confirmed",
                folio_examples=match.value.get("folio_examples"),
                folio_notes=match.value.get("folio_notes"),
                folio_see_also=match.value.get("folio_see_also"),
                folio_source=match.value.get("folio_source"),
                folio_alt_labels=match.value.get("folio_alt_labels"),
            )

            # Build backup ConceptMatch objects from runner-up candidates
            backup_concepts: list[ConceptMatch] = []
            for bc in match.value.get("_backup_candidates", []):
                backup_concepts.append(ConceptMatch(
                    concept_text=bc.get("concept_text", ""),
                    folio_iri=bc.get("folio_iri"),
                    folio_label=bc.get("folio_label"),
                    folio_definition=bc.get("folio_definition"),
                    branches=bc.get("branches", []),
                    branch_color=bc.get("branch_color"),
                    confidence=bc.get("confidence", 0.0),
                    source=bc.get("source", "matched"),
                    state="backup",
                    iri_hash=bc.get("iri_hash"),
                    folio_alt_labels=bc.get("folio_alt_labels"),
                ))

            # Materialize upstream _lineage_events from resolved concept dicts
            upstream_events: list[StageEvent] = []
            for evt in match.value.get("_lineage_events", []):
                upstream_events.append(StageEvent(
                    stage=evt.get("stage", ""),
                    action=evt.get("action", ""),
                    detail=evt.get("detail", ""),
                    confidence=evt.get("confidence"),
                    timestamp=evt.get("timestamp", ""),
                    reasoning=evt.get("reasoning", ""),
                ))

            if span_key in existing_by_span:
                # Update existing annotation: enrich with resolved FOLIO data
                existing = existing_by_span[span_key]
                existing.concepts = [concept] + backup_concepts
                existing.state = "confirmed"
                # Backfill sentence_text if not already populated
                if not existing.span.sentence_text:
                    existing.span.sentence_text = find_sentence_for_span(
                        sentence_index, match.start, match.end
                    )
                # Preserve existing lineage, then add upstream + this stage
                existing.lineage.extend(upstream_events)
                record_lineage(existing, "string_matching", "confirmed",
                               detail="Aho-Corasick span match, enriched with FOLIO data")
                new_annotations.append(existing)
            else:
                # New span from Aho-Corasick
                ann = Annotation(
                    span=Span(
                        start=match.start,
                        end=match.end,
                        text=full_text[match.start:match.end],
                        sentence_text=find_sentence_for_span(sentence_index, match.start, match.end),
                    ),
                    concepts=[concept] + backup_concepts,
                    state="confirmed",
                    lineage=upstream_events,
                )
                record_lineage(ann, "string_matching", "confirmed",
                               detail="Aho-Corasick span match, enriched with FOLIO data")
                new_annotations.append(ann)

        # Keep rejected annotations (for frontend strikethrough display)
        for ann in job.result.annotations:
            span_key = (ann.span.start, ann.span.end)
            if span_key not in seen_spans and ann.state == "rejected":
                new_annotations.append(ann)

        # Sort by span start
        new_annotations.sort(key=lambda a: a.span.start)

        updated = sum(1 for s in seen_spans if s in existing_by_span)
        new_count = len([a for a in new_annotations if a.state == "confirmed"]) - updated
        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"Annotated {len(new_annotations)} spans ({updated} updated, {max(0, new_count)} new)"})

        job.result.annotations = new_annotations
        return job
