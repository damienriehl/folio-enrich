from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.concept.llm_concept_identifier import LLMConceptIdentifier
from app.services.llm.base import LLMProvider
from app.services.matching.aho_corasick import AhoCorasickMatcher
from app.services.normalization.normalizer import build_sentence_index, find_sentence_for_span


class LLMConceptStage(PipelineStage):
    def __init__(self, llm: LLMProvider) -> None:
        self.identifier = LLMConceptIdentifier(llm)

    @property
    def name(self) -> str:
        return "llm_concept_identification"

    async def execute(self, job: Job) -> Job:
        job.status = JobStatus.IDENTIFYING
        if job.result.canonical_text is None:
            return job

        chunks = job.result.canonical_text.chunks
        results = await self.identifier.identify_concepts_batch(chunks)

        # Store raw LLM concepts in metadata for later reconciliation
        llm_concepts: dict[str, list[dict]] = {}
        for k, v in results.items():
            chunk_list = []
            for c in v:
                d = c.model_dump()
                d["_lineage_event"] = {
                    "stage": "llm_concept",
                    "action": "identified",
                    "detail": f"LLM extracted from chunk {k}",
                    "confidence": c.confidence,
                }
                chunk_list.append(d)
            llm_concepts[str(k)] = chunk_list
        job.result.metadata["llm_concepts"] = llm_concepts

        # Build preliminary annotations via Aho-Corasick span matching
        all_concepts = [c for chunk in results.values() for c in chunk]
        preliminary = self._build_preliminary_annotations(
            all_concepts, job.result.canonical_text.full_text
        )
        job.result.metadata["llm_preliminary_annotations"] = preliminary

        total = sum(len(v) for v in results.values())
        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"LLM extracted {total} concepts from {len(chunks)} chunks ({len(preliminary)} preliminary spans)"})
        return job

    @staticmethod
    def _build_preliminary_annotations(concepts, full_text: str) -> list[dict]:
        """Find spans for LLM-extracted concepts via Aho-Corasick and return serialized Annotation dicts."""
        if not concepts or not full_text:
            return []

        # Deduplicate concept texts, keeping highest confidence per text
        best_by_text: dict[str, object] = {}
        for c in concepts:
            key = c.concept_text.lower()
            if key not in best_by_text or c.confidence > best_by_text[key].confidence:
                best_by_text[key] = c

        matcher = AhoCorasickMatcher()
        for text_key, concept in best_by_text.items():
            matcher.add_pattern(text_key, {"concept": concept})
        matcher.build()

        matches = matcher.search(full_text)
        if not matches:
            return []

        sentence_index = build_sentence_index(full_text)
        annotations: list[dict] = []

        for m in matches:
            concept = m.value.get("concept") if isinstance(m.value, dict) else None
            if concept is None:
                continue
            annotations.append({
                "id": str(uuid4()),
                "span": {
                    "start": m.start,
                    "end": m.end,
                    "text": full_text[m.start:m.end],
                    "sentence_text": find_sentence_for_span(sentence_index, m.start, m.end),
                },
                "concepts": [{
                    "concept_text": concept.concept_text,
                    "folio_iri": concept.folio_iri,
                    "branches": concept.branches if hasattr(concept, "branches") else [],
                    "confidence": concept.confidence,
                    "source": "llm",
                    "state": "preliminary",
                }],
                "state": "preliminary",
                "source": "llm",
            })

        return annotations
