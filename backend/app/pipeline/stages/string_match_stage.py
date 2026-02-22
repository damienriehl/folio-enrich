from __future__ import annotations

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

        # Convert matches to annotations
        annotations: list[Annotation] = []
        for match in matches:
            annotations.append(
                Annotation(
                    span=Span(
                        start=match.start,
                        end=match.end,
                        text=full_text[match.start : match.end],
                    ),
                    concepts=[
                        ConceptMatch(
                            concept_text=match.value.get("concept_text", match.pattern),
                            folio_iri=match.value.get("folio_iri"),
                            folio_label=match.value.get("folio_label"),
                            folio_definition=match.value.get("folio_definition"),
                            branch=match.value.get("branch"),
                            confidence=match.value.get("confidence", 0.0),
                            source=match.value.get("source", "matched"),
                        )
                    ],
                )
            )

        job.result.annotations = annotations
        return job
