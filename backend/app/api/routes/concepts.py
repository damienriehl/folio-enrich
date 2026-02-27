"""API routes for FOLIO concept lookup and entity graph."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/concepts", tags=["concepts"])

MAX_BATCH_SIZE = 100


def _get_folio():
    """Get the raw FOLIO instance."""
    from app.services.folio.folio_service import FolioService
    return FolioService.get_instance()._get_folio()


class BatchRequest(BaseModel):
    iri_hashes: list[str] = Field(..., max_length=MAX_BATCH_SIZE)


@router.post("/batch")
async def get_concepts_batch(body: BatchRequest) -> dict:
    """Look up multiple FOLIO concepts by IRI hash in one call.

    Returns a mapping of iri_hash → detail for each found concept.
    Unknown hashes are silently omitted.
    """
    from app.services.folio.concept_detail import lookup_concept_detail

    folio = _get_folio()
    results: dict[str, dict] = {}
    for iri_hash in body.iri_hashes[:MAX_BATCH_SIZE]:
        detail = lookup_concept_detail(folio, iri_hash)
        if detail is not None:
            results[iri_hash] = detail.model_dump()
    return results


@router.get("/{iri_hash}")
async def get_concept_detail(iri_hash: str) -> dict:
    """Look up a FOLIO concept by IRI hash with full detail."""
    from app.services.folio.concept_detail import lookup_concept_detail

    folio = _get_folio()
    detail = lookup_concept_detail(folio, iri_hash)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Concept not found: {iri_hash}")
    return detail.model_dump()


@router.get("/{iri_hash}/graph")
async def get_concept_graph(
    iri_hash: str,
    ancestors_depth: int = 2,
    descendants_depth: int = 2,
    max_nodes: int = 200,
    include_see_also: bool = True,
) -> dict:
    """Build an entity graph around a FOLIO concept via BFS."""
    from app.services.folio.concept_detail import build_entity_graph

    folio = _get_folio()
    graph = build_entity_graph(
        folio, iri_hash,
        ancestors_depth=ancestors_depth,
        descendants_depth=descendants_depth,
        max_nodes=max_nodes,
        include_see_also=include_see_also,
    )
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Concept not found: {iri_hash}")
    return graph.model_dump()
