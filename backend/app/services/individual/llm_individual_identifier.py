"""Pass 3 — LLM-based individual extraction and class linking."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.models.annotation import (
    Annotation,
    Individual,
    IndividualClassLink,
    Span,
    StageEvent,
)
from app.models.document import TextChunk
from app.services.llm.base import LLMProvider
from app.services.llm.prompts.individual_extraction import (
    build_individual_extraction_prompt,
)

logger = logging.getLogger(__name__)


class LLMIndividualIdentifier:
    """Uses LLM to extract individuals and link them to OWL class annotations."""

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def identify_individuals(
        self,
        chunk: TextChunk,
        annotations: list[Annotation],
        existing_individuals: list[Individual],
    ) -> list[Individual]:
        """Extract individuals from a single chunk using LLM."""
        # Build class annotation context for this chunk
        chunk_start = chunk.start_offset
        chunk_end = chunk.end_offset

        class_annotations = []
        for ann in annotations:
            # Include annotations whose spans overlap this chunk
            if ann.span.end > chunk_start and ann.span.start < chunk_end:
                if ann.concepts:
                    top = ann.concepts[0]
                    class_annotations.append({
                        "id": ann.id,
                        "label": top.folio_label or top.concept_text,
                        "span_text": ann.span.text,
                        "branch": top.branches[0] if top.branches else "",
                    })

        # Build existing individual context for this chunk
        existing_ind_context = []
        for ind in existing_individuals:
            if ind.span.end > chunk_start and ind.span.start < chunk_end:
                existing_ind_context.append({
                    "name": ind.name,
                    "type": ind.individual_type,
                    "source": ind.source,
                })

        prompt = build_individual_extraction_prompt(
            chunk.text, class_annotations, existing_ind_context
        )

        try:
            result = await self.llm.structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "individuals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "mention_text": {"type": "string"},
                                    "individual_type": {"type": "string"},
                                    "class_annotation_ids": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "class_labels": {
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
                "LLM individual identification failed for chunk %d",
                chunk.chunk_index,
            )
            return []

        new_individuals: list[Individual] = []
        ann_by_id = {a.id: a for a in annotations}

        for item in result.get("individuals", []):
            is_new = item.get("is_new", True)

            if not is_new:
                # This is a class-linking update for an existing individual
                # We return a "link instruction" that the deduplicator merges
                self._apply_class_links(
                    existing_individuals,
                    item,
                    ann_by_id,
                    chunk_start,
                    chunk_end,
                )
                continue

            # New individual from LLM
            mention_text = item.get("mention_text", "")
            if not mention_text:
                continue

            # Find span in chunk text, then offset to document coordinates
            pos = chunk.text.find(mention_text)
            if pos < 0:
                # Try case-insensitive
                pos = chunk.text.lower().find(mention_text.lower())
            if pos < 0:
                continue

            doc_start = chunk_start + pos
            doc_end = doc_start + len(mention_text)

            # Build class links
            class_links = self._build_class_links(item, ann_by_id)
            confidence = max(0.0, min(1.0, item.get("confidence", 0.5)))

            individual = Individual(
                id=str(uuid4()),
                name=item.get("name", mention_text.strip()),
                mention_text=mention_text,
                individual_type=item.get("individual_type", "named_entity"),
                span=Span(start=doc_start, end=doc_end, text=mention_text),
                class_links=class_links,
                confidence=confidence,
                source="llm",
                lineage=[
                    StageEvent(
                        stage="individual_extraction",
                        action="created",
                        detail="llm: individual extraction",
                        confidence=confidence,
                    )
                ],
            )
            new_individuals.append(individual)

        return new_individuals

    def _build_class_links(
        self,
        item: dict,
        ann_by_id: dict[str, Annotation],
    ) -> list[IndividualClassLink]:
        """Build IndividualClassLink objects from LLM output."""
        links: list[IndividualClassLink] = []
        ann_ids = item.get("class_annotation_ids", [])
        labels = item.get("class_labels", [])
        confidence = max(0.0, min(1.0, item.get("confidence", 0.5)))

        # Link by annotation ID
        for ann_id in ann_ids:
            ann = ann_by_id.get(ann_id)
            if ann and ann.concepts:
                top = ann.concepts[0]
                links.append(
                    IndividualClassLink(
                        annotation_id=ann_id,
                        folio_iri=top.folio_iri,
                        folio_label=top.folio_label,
                        branch=top.branches[0] if top.branches else "",
                        relationship="instance_of",
                        confidence=confidence,
                    )
                )

        # Also add by label (for cases without matching annotation IDs)
        existing_labels = {l.folio_label for l in links}
        for label in labels:
            if label not in existing_labels:
                links.append(
                    IndividualClassLink(
                        folio_label=label,
                        relationship="instance_of",
                        confidence=confidence,
                    )
                )

        return links

    def _apply_class_links(
        self,
        existing_individuals: list[Individual],
        item: dict,
        ann_by_id: dict[str, Annotation],
        chunk_start: int,
        chunk_end: int,
    ) -> None:
        """Apply LLM class links to existing individuals in-place."""
        mention = item.get("mention_text", "")
        name = item.get("name", mention)

        # Find matching existing individual
        for ind in existing_individuals:
            if ind.span.end <= chunk_start or ind.span.start >= chunk_end:
                continue
            if ind.name.lower() == name.lower() or ind.mention_text.lower() == mention.lower():
                new_links = self._build_class_links(item, ann_by_id)
                existing_link_keys = {
                    (l.annotation_id, l.folio_label) for l in ind.class_links
                }
                for link in new_links:
                    if (link.annotation_id, link.folio_label) not in existing_link_keys:
                        ind.class_links.append(link)
                        ind.lineage.append(
                            StageEvent(
                                stage="individual_extraction",
                                action="linked",
                                detail=f"llm: linked to {link.folio_label}",
                                confidence=link.confidence,
                            )
                        )
                break

    async def identify_batch(
        self,
        chunks: list[TextChunk],
        annotations: list[Annotation],
        existing_individuals: list[Individual],
    ) -> list[Individual]:
        """Process all chunks in parallel, returning new individuals."""
        tasks = [
            self.identify_individuals(chunk, annotations, existing_individuals)
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_new: list[Individual] = []
        for chunk, result in zip(chunks, results):
            if isinstance(result, Exception):
                logger.error(
                    "LLM individual ID failed for chunk %d: %s",
                    chunk.chunk_index,
                    result,
                )
            else:
                all_new.extend(result)
        return all_new
