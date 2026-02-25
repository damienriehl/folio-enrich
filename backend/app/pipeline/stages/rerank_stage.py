from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.llm.base import LLMProvider
from app.services.llm.prompts.contextual_rerank import build_contextual_rerank_prompt

logger = logging.getLogger(__name__)


class ContextualRerankStage(PipelineStage):
    """LLM-based contextual reranking of resolved concepts.

    Sends a single batched LLM call per document with all concepts and their
    sentence contexts.  The LLM scores each concept's contextual relevance
    using an explicit rubric, and the result is blended 50/50 with the
    existing pipeline score.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @property
    def name(self) -> str:
        return "contextual_rerank"

    async def execute(self, job: Job) -> Job:
        from app.config import settings

        if not settings.contextual_rerank_enabled:
            return job

        resolved = job.result.metadata.get("resolved_concepts", [])
        if not resolved:
            return job

        full_text = ""
        if job.result.canonical_text:
            full_text = job.result.canonical_text.full_text

        if not full_text:
            return job

        prompt = build_contextual_rerank_prompt(full_text, resolved)

        try:
            raw = await self.llm.complete(prompt, temperature=0.0)
            scores_map = self._parse_scores(raw)
        except Exception:
            logger.warning(
                "Contextual rerank LLM call failed for job %s — skipping",
                job.id,
                exc_info=True,
            )
            return job

        # Blend 50/50 with pipeline score
        reranked = 0
        for concept in resolved:
            key = (
                concept.get("concept_text", "").lower(),
                concept.get("folio_iri", ""),
            )
            if key in scores_map:
                ctx_score = scores_map[key]
                pipeline_score = concept.get("confidence", 0.5)
                concept["confidence"] = round(
                    pipeline_score * 0.5 + ctx_score * 0.5, 4
                )
                # Record lineage
                events = concept.setdefault("_lineage_events", [])
                events.append({
                    "stage": "contextual_rerank",
                    "action": "reranked",
                    "detail": f"LLM context score={ctx_score:.2f}, blended 50/50",
                    "confidence": concept["confidence"],
                })
                reranked += 1

        log = job.result.metadata.setdefault("activity_log", [])
        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "msg": f"Contextually reranked {reranked}/{len(resolved)} concepts",
        })
        logger.info(
            "Contextual rerank: scored %d/%d concepts for job %s",
            reranked, len(resolved), job.id,
        )
        return job

    @staticmethod
    def _parse_scores(raw: str) -> dict[tuple[str, str], float]:
        """Parse LLM response into {(concept_text, folio_iri): score} map."""
        scores: dict[tuple[str, str], float] = {}
        try:
            # Try to extract JSON from response
            text = raw.strip()
            # Handle markdown code blocks
            if "```" in text:
                start = text.find("```")
                end = text.rfind("```")
                if start != end:
                    inner = text[start:end]
                    # Remove language tag
                    first_newline = inner.find("\n")
                    if first_newline >= 0:
                        text = inner[first_newline + 1:]

            data = json.loads(text)
            items = data.get("scores", []) if isinstance(data, dict) else data
            for item in items:
                ct = item.get("concept_text", "").lower()
                iri = item.get("folio_iri", "")
                score = float(item.get("contextual_score", 0.5))
                score = max(0.0, min(1.0, score))
                scores[(ct, iri)] = score
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            logger.debug("Failed to parse rerank scores", exc_info=True)
        return scores
