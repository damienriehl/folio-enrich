"""Early document type identification — parallel stage.

Asks the LLM what the document calls *itself* (verbatim from title/caption/header).
Stores the result in job metadata so all downstream stages can use it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.job import Job
from app.pipeline.stages.base import PipelineStage
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_DOCUMENT_TYPE_PROMPT = """You are a legal document analyst. Read the beginning of this document and determine what type of document it identifies itself as.

Extract the VERBATIM document type as the document describes itself — use the full, specific label from the document's title, caption, or header. Do NOT normalize or simplify.

Examples of good self_identified_type values:
- "Defendant's Motion to Dismiss Under Rule 12(b)(6) for Failure to State a Claim"
- "Verified Complaint for Declaratory and Injunctive Relief"
- "Commercial Lease Agreement"
- "Memorandum of Law in Support of Plaintiff's Motion for Summary Judgment"
- "Order Granting in Part and Denying in Part Defendant's Motion to Dismiss"

If the document does not clearly identify its type, use your best judgment based on its structure and content.

Respond with JSON:
{{"self_identified_type": "...", "confidence": 0.95, "reasoning": "brief explanation of where you found this"}}

DOCUMENT TEXT (first 500 chars):
{text}"""


class DocumentTypeStage(PipelineStage):
    """Identifies what the document calls itself, early in the pipeline.

    Runs in parallel with EntityRuler, LLMConcept, EarlyIndividual, and
    EarlyProperty.  The result is stored in ``job.result.metadata`` for
    use by all post-parallel LLM stages.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @property
    def name(self) -> str:
        return "document_type_classification"

    async def execute(self, job: Job) -> Job:
        if not job.result.canonical_text:
            return job

        full_text = job.result.canonical_text.full_text
        if not full_text:
            return job

        snippet = full_text[:500]
        prompt = _DOCUMENT_TYPE_PROMPT.replace("{text}", snippet)

        try:
            result = await self.llm.structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "self_identified_type": {"type": "string"},
                        "confidence": {"type": "number"},
                        "reasoning": {"type": "string"},
                    },
                },
            )
        except Exception:
            logger.warning(
                "Early document type classification failed for job %s",
                job.id,
                exc_info=True,
            )
            return job

        self_type = result.get("self_identified_type", "")
        confidence = result.get("confidence", 0.0)

        if self_type:
            job.result.metadata["self_identified_type"] = self_type
            job.result.metadata["document_type"] = self_type
            job.result.metadata["document_type_confidence"] = confidence

            log = job.result.metadata.setdefault("activity_log", [])
            conf_pct = round(confidence * 100)
            log.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "stage": self.name,
                "msg": f"Document self-identifies as: {self_type} ({conf_pct}% confidence)",
            })

            logger.info(
                "Early document type for job %s: %s (%.0f%%)",
                job.id, self_type, confidence * 100,
            )

        return job
