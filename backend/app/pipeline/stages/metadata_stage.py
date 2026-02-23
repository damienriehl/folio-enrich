from __future__ import annotations

from datetime import datetime, timezone

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.llm.base import LLMProvider
from app.services.metadata.classifier import DocumentClassifier
from app.services.metadata.extractor import MetadataExtractor
from app.services.metadata.promoter import MetadataPromoter


class MetadataStage(PipelineStage):
    def __init__(self, llm: LLMProvider) -> None:
        self.classifier = DocumentClassifier(llm)
        self.extractor = MetadataExtractor(llm)
        self.promoter = MetadataPromoter()

    @property
    def name(self) -> str:
        return "metadata"

    async def execute(self, job: Job) -> Job:
        if job.result.canonical_text is None:
            return job

        full_text = job.result.canonical_text.full_text

        # Phase 1: Classify document type
        classification = await self.classifier.classify(full_text)
        doc_type = classification.get("document_type", "Unknown")

        # Phase 2: Extract structured fields
        fields = await self.extractor.extract(full_text, doc_type)

        # Phase 3: Promote annotations to metadata (runs after annotations exist)
        if job.result.annotations:
            fields = self.promoter.promote(
                job.result.annotations, full_text, fields
            )

        # Store in job metadata
        job.result.metadata["document_type"] = doc_type
        job.result.metadata["document_type_confidence"] = classification.get("confidence", 0.0)
        job.result.metadata["extracted_fields"] = fields

        conf = round(classification.get("confidence", 0.0) * 100)
        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"Classified as {doc_type} ({conf}% confidence)"})
        return job
