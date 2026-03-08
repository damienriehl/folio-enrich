"""OWL Update Manager — background checking, download, and hot-reload.

Singleton service that orchestrates the full FOLIO OWL update lifecycle:
1. HEAD probe to check for new version
2. Download + XML validation
3. Wait for idle pipeline (no active jobs)
4. Hot-reload FolioService caches
5. Re-index embeddings
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_IDLE_WAIT_TIMEOUT = 300  # 5 minutes max wait for idle pipeline
_IDLE_POLL_INTERVAL = 5   # seconds between active-job checks


@dataclass
class OWLUpdateStatus:
    last_check_at: str | None = None
    last_update_at: str | None = None
    update_available: bool = False
    update_in_progress: bool = False
    next_check_at: str | None = None
    current_etag: str | None = None
    concepts_before: int | None = None
    concepts_after: int | None = None
    error: str | None = None


class OWLUpdateManager:
    """Singleton manager for FOLIO OWL ontology updates."""

    _instance: OWLUpdateManager | None = None

    def __init__(self) -> None:
        self._status = OWLUpdateStatus()

    @classmethod
    def get_instance(cls) -> OWLUpdateManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    def get_status(self) -> dict:
        """Return current update status as a dict."""
        return asdict(self._status)

    async def check(self) -> bool:
        """HEAD-only probe. Returns True if an update is available."""
        from app.services.folio.owl_cache import check_owl_freshness, get_owl_status

        try:
            loop = asyncio.get_event_loop()
            is_stale, new_etag = await loop.run_in_executor(None, check_owl_freshness)

            self._status.last_check_at = datetime.now(timezone.utc).isoformat()
            self._status.current_etag = get_owl_status().get("etag")
            self._status.error = None

            if is_stale:
                self._status.update_available = True
                logger.info("FOLIO OWL update available (new etag: %s)", new_etag)
            else:
                self._status.update_available = False

            return is_stale
        except Exception as exc:
            self._status.error = str(exc)
            logger.warning("OWL update check failed: %s", exc, exc_info=True)
            return False

    async def apply(self) -> dict | None:
        """Download, validate, wait for idle, reload, and re-index.

        Returns reload stats dict on success, None on failure or nothing to do.
        """
        if self._status.update_in_progress:
            logger.warning("OWL update already in progress")
            return None

        self._status.update_in_progress = True
        self._status.error = None
        try:
            return await self._do_apply()
        except Exception as exc:
            self._status.error = str(exc)
            logger.warning("OWL update apply failed: %s", exc, exc_info=True)
            return None
        finally:
            self._status.update_in_progress = False

    async def _do_apply(self) -> dict | None:
        loop = asyncio.get_event_loop()

        # Step 1: Download + validate (ensure_owl_fresh handles atomic write)
        from app.services.folio.owl_cache import ensure_owl_fresh
        await loop.run_in_executor(None, ensure_owl_fresh)

        # Step 2: Wait for idle pipeline
        from app.storage.job_store import JobStore
        store = JobStore()
        waited = 0
        while waited < _IDLE_WAIT_TIMEOUT:
            active = await store.count_active()
            if active == 0:
                break
            logger.info("Waiting for %d active job(s) before OWL reload...", active)
            await asyncio.sleep(_IDLE_POLL_INTERVAL)
            waited += _IDLE_POLL_INTERVAL
        else:
            self._status.error = "Timed out waiting for active jobs to complete"
            logger.warning("OWL update deferred: active jobs still running after %ds", _IDLE_WAIT_TIMEOUT)
            return None

        # Step 3: Reload FolioService
        from app.services.folio.folio_service import FolioService
        folio_svc = FolioService.get_instance()
        reload_stats = await loop.run_in_executor(None, folio_svc._reload)

        # Step 4: Re-index embeddings
        try:
            from app.services.embedding.service import EmbeddingService, build_embedding_index
            emb_svc = EmbeddingService.get_instance()
            await loop.run_in_executor(None, emb_svc.index_folio_labels, folio_svc)
            await loop.run_in_executor(None, build_embedding_index, folio_svc)
            logger.info("Embedding index rebuilt after OWL update")
        except Exception:
            logger.warning("Embedding re-index failed after OWL update", exc_info=True)

        # Step 5: Update status
        from app.services.folio.owl_cache import get_owl_status
        self._status.last_update_at = datetime.now(timezone.utc).isoformat()
        self._status.update_available = False
        self._status.current_etag = get_owl_status().get("etag")
        self._status.concepts_before = reload_stats.get("concepts_before")
        self._status.concepts_after = reload_stats.get("concepts_after")

        logger.info(
            "FOLIO ontology updated: %d → %d concepts",
            reload_stats.get("concepts_before", 0),
            reload_stats.get("concepts_after", 0),
        )
        return reload_stats

    async def check_and_apply(self) -> dict | None:
        """Check for update and apply if available. Returns reload stats or None."""
        is_stale = await self.check()
        if not is_stale:
            return None
        return await self.apply()

    async def rollback(self) -> dict | None:
        """Roll back to previous OWL version and reload."""
        if self._status.update_in_progress:
            logger.warning("Cannot rollback while update is in progress")
            return None

        self._status.update_in_progress = True
        self._status.error = None
        try:
            loop = asyncio.get_event_loop()

            from app.services.folio.owl_cache import rollback_owl
            await loop.run_in_executor(None, rollback_owl)

            from app.services.folio.folio_service import FolioService
            folio_svc = FolioService.get_instance()
            reload_stats = await loop.run_in_executor(None, folio_svc._reload)

            # Re-index embeddings
            try:
                from app.services.embedding.service import EmbeddingService, build_embedding_index
                emb_svc = EmbeddingService.get_instance()
                await loop.run_in_executor(None, emb_svc.index_folio_labels, folio_svc)
                await loop.run_in_executor(None, build_embedding_index, folio_svc)
            except Exception:
                logger.warning("Embedding re-index failed after rollback", exc_info=True)

            from app.services.folio.owl_cache import get_owl_status
            self._status.last_update_at = datetime.now(timezone.utc).isoformat()
            self._status.update_available = False
            self._status.current_etag = get_owl_status().get("etag")
            self._status.concepts_before = reload_stats.get("concepts_before")
            self._status.concepts_after = reload_stats.get("concepts_after")

            logger.info("FOLIO ontology rolled back: %d → %d concepts",
                        reload_stats.get("concepts_before", 0),
                        reload_stats.get("concepts_after", 0))
            return reload_stats
        except FileNotFoundError as exc:
            self._status.error = str(exc)
            return None
        except Exception as exc:
            self._status.error = str(exc)
            logger.warning("OWL rollback failed: %s", exc, exc_info=True)
            return None
        finally:
            self._status.update_in_progress = False
