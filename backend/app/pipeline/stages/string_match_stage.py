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
        # Key on (text, IRI) to support multi-branch — same text with different IRIs
        concept_map: dict[tuple[str, str], dict] = {}
        # Track which text patterns are in the automaton (add each text once)
        text_patterns_added: set[str] = set()

        for rc in resolved_concepts:
            key = (rc["concept_text"].lower(), rc.get("folio_iri", ""))
            if key not in concept_map or rc["confidence"] > concept_map[key]["confidence"]:
                concept_map[key] = rc

            # Also add alt labels and hidden label as patterns pointing to same data
            alt_labels = rc.get("folio_alt_labels") or []
            for alt in alt_labels:
                alt_key = (alt.lower(), rc.get("folio_iri", ""))
                if alt_key not in concept_map and self._is_safe_alt_label(alt):
                    concept_map[alt_key] = rc

            hidden = rc.get("folio_hidden_label") or ""
            if hidden:
                hidden_key = (hidden.lower(), rc.get("folio_iri", ""))
                if hidden_key not in concept_map and self._is_safe_alt_label(hidden):
                    concept_map[hidden_key] = rc

        # Build a text→list[dict] map for multi-branch annotation creation
        text_to_concepts: dict[str, list[dict]] = {}
        for (text_key, iri), data in concept_map.items():
            text_to_concepts.setdefault(text_key, []).append(data)

        for (text_key, iri), data in concept_map.items():
            if text_key not in text_patterns_added:
                matcher.add_pattern(text_key, data)
                text_patterns_added.add(text_key)
        matcher.build()

        # Search full canonical text
        full_text = job.result.canonical_text.full_text
        sentence_index = build_sentence_index(full_text)
        matches = matcher.search(full_text)

        # Build lookup of existing annotations by (span, IRI) for merging
        existing_by_span_iri: dict[tuple[int, int, str], Annotation] = {}
        existing_by_span: dict[tuple[int, int], list[Annotation]] = {}
        for ann in job.result.annotations:
            iri = ann.concepts[0].folio_iri if ann.concepts else ""
            existing_by_span_iri[(ann.span.start, ann.span.end, iri or "")] = ann
            existing_by_span.setdefault((ann.span.start, ann.span.end), []).append(ann)

        # Merge Aho-Corasick matches with existing annotations
        new_annotations: list[Annotation] = []
        seen_spans: set[tuple[int, int]] = set()
        seen_span_iris: set[tuple[int, int, str]] = set()

        for match in matches:
            span_key = (match.start, match.end)
            seen_spans.add(span_key)

            # Get all concepts that match this text (multi-branch support)
            all_concept_dicts = text_to_concepts.get(match.pattern.lower(), [match.value])

            for concept_dict in all_concept_dicts:
                concept_iri = concept_dict.get("folio_iri", "")
                span_iri_key = (match.start, match.end, concept_iri)

                if span_iri_key in seen_span_iris:
                    continue
                seen_span_iris.add(span_iri_key)

                concept = ConceptMatch(
                    concept_text=concept_dict.get("concept_text", match.pattern),
                    folio_iri=concept_iri,
                    folio_label=concept_dict.get("folio_label"),
                    folio_definition=concept_dict.get("folio_definition"),
                    branches=concept_dict.get("branches", []),
                    confidence=concept_dict.get("confidence", 0.0),
                    source=concept_dict.get("source", "matched"),
                    state="confirmed",
                    folio_examples=concept_dict.get("folio_examples"),
                    folio_notes=concept_dict.get("folio_notes"),
                    folio_see_also=concept_dict.get("folio_see_also"),
                    folio_source=concept_dict.get("folio_source"),
                    folio_alt_labels=concept_dict.get("folio_alt_labels"),
                )

                # Build backup ConceptMatch objects from runner-up candidates
                backup_concepts: list[ConceptMatch] = []
                for bc in concept_dict.get("_backup_candidates", []):
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
                for evt in concept_dict.get("_lineage_events", []):
                    upstream_events.append(StageEvent(
                        stage=evt.get("stage", ""),
                        action=evt.get("action", ""),
                        detail=evt.get("detail", ""),
                        confidence=evt.get("confidence"),
                        timestamp=evt.get("timestamp", ""),
                        reasoning=evt.get("reasoning", ""),
                    ))

                if span_iri_key in existing_by_span_iri:
                    # Update existing annotation: enrich with resolved FOLIO data
                    existing = existing_by_span_iri[span_iri_key]
                    existing.concepts = [concept] + backup_concepts
                    existing.state = "confirmed"
                    if not existing.span.sentence_text:
                        existing.span.sentence_text = find_sentence_for_span(
                            sentence_index, match.start, match.end
                        )
                    existing.lineage.extend(upstream_events)
                    record_lineage(existing, "string_matching", "confirmed",
                                   detail="Aho-Corasick span match, enriched with FOLIO data")
                    new_annotations.append(existing)
                elif (match.start, match.end) in existing_by_span:
                    # Secondary lookup: match by span + concept text (preserves LLM preliminary annotation IDs)
                    matched_existing = None
                    match_text = concept.concept_text.lower()
                    for candidate in existing_by_span[(match.start, match.end)]:
                        if candidate.concepts and candidate.concepts[0].concept_text.lower() == match_text:
                            matched_existing = candidate
                            break
                    if matched_existing is not None:
                        matched_existing.concepts = [concept] + backup_concepts
                        matched_existing.state = "confirmed"
                        if not matched_existing.span.sentence_text:
                            matched_existing.span.sentence_text = find_sentence_for_span(
                                sentence_index, match.start, match.end
                            )
                        matched_existing.lineage.extend(upstream_events)
                        record_lineage(matched_existing, "string_matching", "confirmed",
                                       detail="Upgraded preliminary annotation with FOLIO data")
                        new_annotations.append(matched_existing)
                    else:
                        # No text match among existing at this span — create new
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
                else:
                    # New span/IRI from Aho-Corasick
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
