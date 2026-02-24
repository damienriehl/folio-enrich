from __future__ import annotations

from datetime import datetime, timezone

from app.models.annotation import Annotation, ConceptMatch, Span
from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.matching.aho_corasick import AhoCorasickMatcher


class StringMatchStage(PipelineStage):
    @property
    def name(self) -> str:
        return "string_matching"

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

        for text, data in concept_map.items():
            matcher.add_pattern(text, data)
        matcher.build()

        # Search full canonical text
        full_text = job.result.canonical_text.full_text
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
            )

            if span_key in existing_by_span:
                # Update existing annotation: enrich with resolved FOLIO data
                existing = existing_by_span[span_key]
                existing.concepts = [concept]
                existing.state = "confirmed"
                new_annotations.append(existing)
            else:
                # New span from Aho-Corasick
                new_annotations.append(
                    Annotation(
                        span=Span(
                            start=match.start,
                            end=match.end,
                            text=full_text[match.start:match.end],
                        ),
                        concepts=[concept],
                        state="confirmed",
                    )
                )

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
