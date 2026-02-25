from __future__ import annotations

from datetime import datetime, timezone

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.concept.branch_judge import BranchJudge
from app.services.llm.base import LLMProvider


class BranchJudgeStage(PipelineStage):
    def __init__(self, llm: LLMProvider) -> None:
        self.judge = BranchJudge(llm)

    @property
    def name(self) -> str:
        return "branch_judge"

    async def execute(self, job: Job) -> Job:
        job.status = JobStatus.JUDGING

        # Find concepts that need branch disambiguation
        resolved = job.result.metadata.get("resolved_concepts", [])
        ambiguous = [c for c in resolved if not c.get("branches")]

        if not ambiguous or job.result.canonical_text is None:
            return job

        # Build judge items with sentence context
        full_text = job.result.canonical_text.full_text
        judge_items = []
        for concept in ambiguous:
            # Find sentence containing this concept
            concept_text = concept.get("concept_text", "")
            idx = full_text.lower().find(concept_text.lower())
            if idx >= 0:
                # Extract surrounding sentence (rough heuristic)
                start = max(0, full_text.rfind(".", 0, idx) + 1)
                end = full_text.find(".", idx + len(concept_text))
                if end == -1:
                    end = len(full_text)
                else:
                    end += 1
                sentence = full_text[start:end].strip()
            else:
                sentence = concept_text

            judge_items.append({
                "concept_text": concept_text,
                "sentence": sentence,
                "candidate_branches": [],  # Let judge pick from all branches
            })

        if judge_items:
            results = await self.judge.judge_batch(judge_items)
            # Update concepts with judge decisions
            for concept, result in zip(ambiguous, results):
                if isinstance(result, dict):
                    branch = result.get("branch", "")
                    concept["branches"] = [branch] if branch else []
                    # Weighted blend: 70% pipeline score + 30% judge score
                    existing_conf = concept.get("confidence", 0)
                    judge_conf = result.get("confidence", 0)
                    concept["confidence"] = existing_conf * 0.7 + judge_conf * 0.3
                    # Judge validates → confirmed; no branch found → rejected
                    concept["state"] = "confirmed" if branch else "rejected"
                    # Record lineage event
                    events = concept.setdefault("_lineage_events", [])
                    if branch:
                        events.append({
                            "stage": "branch_judge",
                            "action": "branch_assigned",
                            "detail": f"LLM judge assigned branch '{branch}'",
                            "confidence": result.get("confidence"),
                            "reasoning": result.get("reasoning", ""),
                        })
                    else:
                        events.append({
                            "stage": "branch_judge",
                            "action": "rejected",
                            "detail": "LLM judge could not assign a branch",
                            "confidence": result.get("confidence"),
                            "reasoning": result.get("reasoning", ""),
                        })

        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"Judged {len(ambiguous)} ambiguous concepts for branch assignment"})
        return job
