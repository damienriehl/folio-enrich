"""LLM-based property extraction and domain/range linking."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.models.annotation import (
    Annotation,
    PropertyAnnotation,
    Span,
    StageEvent,
)
from app.models.document import TextChunk
from app.services.folio.folio_service import FolioService
from app.services.llm.base import LLMProvider
from app.services.llm.prompts.property_extraction import (
    build_property_extraction_prompt,
)

logger = logging.getLogger(__name__)


class LLMPropertyIdentifier:
    """Uses LLM to extract properties and link them to domain/range classes."""

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def identify_properties(
        self,
        chunk: TextChunk,
        annotations: list[Annotation],
        existing_properties: list[PropertyAnnotation],
    ) -> list[PropertyAnnotation]:
        """Extract properties from a single chunk using LLM."""
        chunk_start = chunk.start_offset
        chunk_end = chunk.end_offset

        # Build class annotation context for this chunk
        class_annotations = []
        for ann in annotations:
            if ann.span.end > chunk_start and ann.span.start < chunk_end:
                if ann.concepts:
                    top = ann.concepts[0]
                    class_annotations.append({
                        "id": ann.id,
                        "label": top.folio_label or top.concept_text,
                        "span_text": ann.span.text,
                        "branch": top.branches[0] if top.branches else "",
                    })

        # Build existing property context for this chunk
        existing_prop_context = []
        for prop in existing_properties:
            if prop.span.end > chunk_start and prop.span.start < chunk_end:
                existing_prop_context.append({
                    "property_text": prop.property_text,
                    "folio_label": prop.folio_label,
                    "source": prop.source,
                })

        # Get available property labels for reference
        try:
            svc = FolioService.get_instance()
            all_prop_labels = svc.get_all_property_labels()
            property_labels = sorted({info.matched_label for info in all_prop_labels.values()})
        except Exception:
            property_labels = []

        prompt = build_property_extraction_prompt(
            chunk.text, class_annotations, existing_prop_context, property_labels
        )

        try:
            result = await self.llm.structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "properties": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "property_text": {"type": "string"},
                                    "folio_label": {"type": "string"},
                                    "domain_annotation_ids": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "range_annotation_ids": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "confidence": {"type": "number"},
                                    "is_new": {"type": "boolean"},
                                },
                            },
                        }
                    },
                },
            )
        except Exception:
            logger.exception(
                "LLM property identification failed for chunk %d",
                chunk.chunk_index,
            )
            return []

        new_properties: list[PropertyAnnotation] = []
        ann_by_id = {a.id: a for a in annotations}

        # Resolve FOLIO property data for LLM-suggested labels
        try:
            svc = FolioService.get_instance()
            all_prop_labels = svc.get_all_property_labels()
        except Exception:
            all_prop_labels = {}

        for item in result.get("properties", []):
            is_new = item.get("is_new", True)

            if not is_new:
                # Enrich existing property with domain/range from LLM
                self._apply_domain_range(
                    existing_properties, item, ann_by_id, chunk_start, chunk_end
                )
                continue

            # New property from LLM
            prop_text = item.get("property_text", "")
            if not prop_text:
                continue

            # Find span in chunk text
            pos = chunk.text.find(prop_text)
            if pos < 0:
                pos = chunk.text.lower().find(prop_text.lower())
            if pos < 0:
                continue

            doc_start = chunk_start + pos
            doc_end = doc_start + len(prop_text)
            confidence = max(0.0, min(1.0, item.get("confidence", 0.5)))

            # Try to resolve FOLIO property from label
            folio_label = item.get("folio_label", "")
            folio_iri = None
            folio_definition = None
            folio_examples = None
            folio_alt_labels = None
            domain_iris: list[str] = []
            range_iris: list[str] = []
            inverse_of = None

            if folio_label:
                label_key = folio_label.lower()
                if label_key in all_prop_labels:
                    info = all_prop_labels[label_key]
                    folio_iri = info.prop.iri
                    folio_label = info.prop.clean_label
                    folio_definition = info.prop.definition
                    folio_examples = info.prop.examples
                    folio_alt_labels = info.prop.clean_alt_labels
                    domain_iris = info.prop.domain_iris or []
                    range_iris = info.prop.range_iris or []
                    inverse_of = info.prop.inverse_of

            new_properties.append(PropertyAnnotation(
                id=str(uuid4()),
                property_text=prop_text,
                folio_iri=folio_iri,
                folio_label=folio_label or None,
                folio_definition=folio_definition,
                folio_examples=folio_examples,
                folio_alt_labels=folio_alt_labels,
                domain_iris=domain_iris,
                range_iris=range_iris,
                inverse_of_iri=inverse_of,
                span=Span(start=doc_start, end=doc_end, text=prop_text),
                confidence=confidence,
                source="llm",
                lineage=[
                    StageEvent(
                        stage="property_extraction",
                        action="created",
                        detail="llm: property extraction",
                        confidence=confidence,
                    )
                ],
            ))

        return new_properties

    def _apply_domain_range(
        self,
        existing_properties: list[PropertyAnnotation],
        item: dict,
        ann_by_id: dict[str, Annotation],
        chunk_start: int,
        chunk_end: int,
    ) -> None:
        """Apply LLM domain/range links to existing properties in-place."""
        prop_text = item.get("property_text", "")

        for prop in existing_properties:
            if prop.span.end <= chunk_start or prop.span.start >= chunk_end:
                continue
            if prop.property_text.lower() == prop_text.lower():
                # Add domain/range annotation references to lineage
                domain_ids = item.get("domain_annotation_ids", [])
                range_ids = item.get("range_annotation_ids", [])

                detail_parts = []
                if domain_ids:
                    detail_parts.append(f"domain: {domain_ids}")
                if range_ids:
                    detail_parts.append(f"range: {range_ids}")

                if detail_parts:
                    prop.lineage.append(StageEvent(
                        stage="property_extraction",
                        action="enriched",
                        detail=f"llm: linked {', '.join(detail_parts)}",
                        confidence=item.get("confidence", 0.5),
                    ))
                break

    async def identify_batch(
        self,
        chunks: list[TextChunk],
        annotations: list[Annotation],
        existing_properties: list[PropertyAnnotation],
    ) -> list[PropertyAnnotation]:
        """Process all chunks in parallel, returning new properties."""
        tasks = [
            self.identify_properties(chunk, annotations, existing_properties)
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_new: list[PropertyAnnotation] = []
        for chunk, result in zip(chunks, results):
            if isinstance(result, Exception):
                logger.error(
                    "LLM property ID failed for chunk %d: %s",
                    chunk.chunk_index, result,
                )
            else:
                all_new.extend(result)
        return all_new
