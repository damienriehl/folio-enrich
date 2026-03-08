"""FOLIO OWL update API routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.services.folio.owl_cache import get_owl_status
from app.services.folio.owl_updater import OWLUpdateManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folio/update", tags=["folio-update"])


@router.get("/status")
async def update_status() -> dict:
    """Current OWL update status + cache info."""
    manager = OWLUpdateManager.get_instance()
    return {
        "update": manager.get_status(),
        "owl_cache": get_owl_status(),
    }


@router.post("/check")
async def check_update() -> dict:
    """Trigger immediate HEAD probe for OWL freshness."""
    manager = OWLUpdateManager.get_instance()
    is_stale = await manager.check()
    return {
        "update_available": is_stale,
        "status": manager.get_status(),
    }


@router.post("/apply")
async def apply_update() -> dict:
    """Apply pending update: download → reload → re-index."""
    manager = OWLUpdateManager.get_instance()
    result = await manager.apply()
    return {
        "applied": result is not None,
        "reload_stats": result,
        "status": manager.get_status(),
    }


@router.post("/rollback")
async def rollback_update() -> dict:
    """Roll back to previous OWL version and reload."""
    manager = OWLUpdateManager.get_instance()
    result = await manager.rollback()
    return {
        "rolled_back": result is not None,
        "reload_stats": result,
        "status": manager.get_status(),
    }
