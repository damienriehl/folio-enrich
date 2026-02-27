from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from app.models.job import Job, JobStatus
from app.pipeline.stages.base import PipelineStage
from app.services.llm.base import LLMProvider
from app.services.metadata.classifier import DocumentClassifier
from app.services.metadata.extractor import MetadataExtractor
from app.services.metadata.promoter import MetadataPromoter

logger = logging.getLogger(__name__)

# Confidence threshold — entities/concepts below this get sentence context
_LOW_CONF_THRESHOLD = 0.80


def _build_context(job: Job) -> dict:
    """Assemble a structured summary of pipeline outputs for the LLM.

    Groups individuals by entity type, includes SPO triples, top concepts,
    areas of law, properties, and document header/footer bookends.
    Low-confidence items include their sentence_text for disambiguation.
    """
    ctx: dict = {}

    # --- Individuals → entities_by_type + low_confidence_entities -----------
    entities_by_type: dict[str, list[str]] = defaultdict(list)
    low_confidence_entities: list[dict] = []
    seen_names: set[str] = set()

    for ind in job.result.individuals:
        name = ind.name or ind.mention_text
        conf = ind.confidence
        # Derive a human-friendly type label from class_links or individual_type
        etype = _individual_type_label(ind)

        if name in seen_names:
            continue
        seen_names.add(name)

        if conf >= _LOW_CONF_THRESHOLD:
            entities_by_type[etype].append(name)
        else:
            entry: dict = {
                "name": name,
                "type": etype,
                "confidence": round(conf, 2),
            }
            if ind.span.sentence_text:
                entry["sentence"] = ind.span.sentence_text
            low_confidence_entities.append(entry)

    if entities_by_type:
        ctx["entities_by_type"] = dict(entities_by_type)
    if low_confidence_entities:
        ctx["low_confidence_entities"] = low_confidence_entities

    # --- Properties → formatted relation strings ----------------------------
    prop_strings: list[str] = []
    seen_props: set[str] = set()
    for prop in job.result.properties:
        label = prop.folio_label or prop.property_text
        if label not in seen_props:
            seen_props.add(label)
            prop_strings.append(f"{label} (text: \"{prop.property_text}\")")
    if prop_strings:
        ctx["properties"] = prop_strings

    # --- SPO triples --------------------------------------------------------
    triples = job.result.metadata.get("spo_triples", [])
    if triples:
        formatted: list[str] = []
        for t in triples[:30]:
            if isinstance(t, dict):
                s = t.get("subject", "?")
                p = t.get("predicate", "?")
                o = t.get("object", "?")
                formatted.append(f"{s} → {p} → {o}")
            elif isinstance(t, str):
                formatted.append(t)
        if formatted:
            ctx["relationships"] = formatted

    # --- Resolved concepts (top 20 by count) --------------------------------
    resolved = job.result.metadata.get("resolved_concepts", [])
    high_concepts: list[str] = []
    low_concepts: list[dict] = []

    for rc in resolved:
        label = rc.get("folio_label") or rc.get("concept_text", "")
        conf = rc.get("confidence", 0.0)
        if not label:
            continue
        if conf >= _LOW_CONF_THRESHOLD:
            if label not in high_concepts:
                high_concepts.append(label)
        else:
            entry = {"label": label, "confidence": round(conf, 2)}
            sent = rc.get("sentence_text", "")
            if sent:
                entry["sentence"] = sent
            low_concepts.append(entry)

    if high_concepts:
        ctx["concepts"] = high_concepts[:20]
    if low_concepts:
        ctx["low_confidence_concepts"] = low_concepts[:15]

    # --- Areas of law -------------------------------------------------------
    areas = job.result.metadata.get("areas_of_law", [])
    if areas:
        ctx["areas_of_law"] = areas

    # --- Document bookends --------------------------------------------------
    full_text = job.result.canonical_text.full_text if job.result.canonical_text else ""
    if full_text:
        ctx["header_text"] = full_text[:1000]
        if len(full_text) > 1500:
            ctx["footer_text"] = full_text[-500:]

    return ctx


def _individual_type_label(ind) -> str:
    """Derive a human-readable type label for an individual."""
    if ind.individual_type == "legal_citation":
        return "Citations"
    # Check class_links for more specific types
    for cl in ind.class_links:
        label = (cl.folio_label or "").lower()
        branch = (cl.branch or "").lower()
        if any(w in label for w in ("person", "human", "individual")):
            return "Persons"
        if any(w in label for w in ("organization", "company", "corporation", "firm", "entity")):
            return "Organizations"
        if any(w in label for w in ("court", "tribunal")):
            return "Courts"
        if any(w in label for w in ("date", "time")):
            return "Dates"
        if any(w in label for w in ("address", "location", "place")):
            return "Addresses"
        if any(w in label for w in ("money", "monetary", "amount", "currency")):
            return "Monetary"
        if branch:
            return branch.title()
    # Fallback based on source
    if ind.source in ("eyecite", "citeurl"):
        return "Citations"
    return "Named Entities"


class MetadataStage(PipelineStage):
    def __init__(
        self,
        llm: LLMProvider,
        *,
        classifier_llm: LLMProvider | None = None,
        extractor_llm: LLMProvider | None = None,
    ) -> None:
        self.classifier = DocumentClassifier(classifier_llm or llm)
        self.extractor = MetadataExtractor(extractor_llm or llm)
        self.promoter = MetadataPromoter()

    @property
    def name(self) -> str:
        return "metadata"

    async def execute(self, job: Job) -> Job:
        if job.result.canonical_text is None:
            return job

        full_text = job.result.canonical_text.full_text

        # Phase 1: Classify document type — reuse early result if available
        early_type = job.result.metadata.get("self_identified_type")
        if early_type:
            doc_type = early_type
            classification = {
                "document_type": early_type,
                "confidence": job.result.metadata.get("document_type_confidence", 0.0),
            }
        else:
            classification = await self.classifier.classify(full_text)
            doc_type = classification.get("document_type", "Unknown")

        # Phase 2: Build structured context from pipeline outputs
        context = _build_context(job)

        # Phase 3: Extract structured fields using pipeline context
        fields = await self.extractor.extract(context, doc_type)

        # Phase 4: Promote annotations to metadata (runs after annotations exist)
        if job.result.annotations:
            fields = self.promoter.promote(
                job.result.annotations, full_text, fields
            )

        # Phase 5: Add deterministic fields
        elements = job.result.canonical_text.elements
        pages = [e.page for e in elements if e.page is not None]
        if pages:
            fields["page_count"] = str(max(pages) + 1)
        fields["source_format"] = job.result.canonical_text.source_format.value

        # Store in job metadata
        job.result.metadata["document_type"] = doc_type
        job.result.metadata["document_type_confidence"] = classification.get("confidence", 0.0)
        job.result.metadata["extracted_fields"] = fields

        conf = round(classification.get("confidence", 0.0) * 100)
        reused = "reused_early=yes" if early_type else "reused_early=no"
        log = job.result.metadata.setdefault("activity_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "stage": self.name, "msg": f"Classified as {doc_type} ({conf}% confidence, {reused})"})
        return job
