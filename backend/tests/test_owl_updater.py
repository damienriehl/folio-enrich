"""Tests for the OWLUpdateManager service."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.folio.owl_updater import OWLUpdateManager, OWLUpdateStatus


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset OWLUpdateManager singleton between tests."""
    OWLUpdateManager.reset_instance()
    yield
    OWLUpdateManager.reset_instance()


class TestSingleton:
    def test_get_instance_returns_same(self):
        a = OWLUpdateManager.get_instance()
        b = OWLUpdateManager.get_instance()
        assert a is b

    def test_reset_instance(self):
        a = OWLUpdateManager.get_instance()
        OWLUpdateManager.reset_instance()
        b = OWLUpdateManager.get_instance()
        assert a is not b


class TestGetStatus:
    def test_initial_status(self):
        manager = OWLUpdateManager.get_instance()
        status = manager.get_status()
        assert status["last_check_at"] is None
        assert status["last_update_at"] is None
        assert status["update_available"] is False
        assert status["update_in_progress"] is False
        assert status["error"] is None

    def test_status_is_dict(self):
        manager = OWLUpdateManager.get_instance()
        status = manager.get_status()
        assert isinstance(status, dict)
        expected_keys = {
            "last_check_at", "last_update_at", "update_available",
            "update_in_progress", "next_check_at", "current_etag",
            "concepts_before", "concepts_after", "error",
        }
        assert set(status.keys()) == expected_keys


class TestCheck:
    @pytest.mark.asyncio
    async def test_check_no_update(self):
        manager = OWLUpdateManager.get_instance()
        with patch("app.services.folio.owl_cache.check_owl_freshness", return_value=(False, None)), \
             patch("app.services.folio.owl_cache.get_owl_status", return_value={"etag": "abc"}):
            result = await manager.check()
        assert result is False
        assert manager._status.update_available is False
        assert manager._status.last_check_at is not None

    @pytest.mark.asyncio
    async def test_check_update_available(self):
        manager = OWLUpdateManager.get_instance()
        with patch("app.services.folio.owl_cache.check_owl_freshness", return_value=(True, "new-etag")), \
             patch("app.services.folio.owl_cache.get_owl_status", return_value={"etag": "old-etag"}):
            result = await manager.check()
        assert result is True
        assert manager._status.update_available is True

    @pytest.mark.asyncio
    async def test_check_error_handled(self):
        manager = OWLUpdateManager.get_instance()
        with patch("app.services.folio.owl_cache.check_owl_freshness", side_effect=RuntimeError("net fail")):
            result = await manager.check()
        assert result is False
        assert "net fail" in manager._status.error


class TestApply:
    @pytest.mark.asyncio
    async def test_apply_success(self):
        manager = OWLUpdateManager.get_instance()
        manager._status.update_available = True

        mock_store = MagicMock()
        mock_store.count_active = AsyncMock(return_value=0)

        mock_folio_svc = MagicMock()
        mock_folio_svc._reload = MagicMock(return_value={"concepts_before": 100, "concepts_after": 105})

        mock_emb_svc = MagicMock()
        mock_emb_svc.index_folio_labels = MagicMock()

        with patch("app.services.folio.owl_cache.ensure_owl_fresh"), \
             patch("app.storage.job_store.JobStore", return_value=mock_store), \
             patch("app.services.folio.folio_service.FolioService.get_instance", return_value=mock_folio_svc), \
             patch("app.services.embedding.service.EmbeddingService.get_instance", return_value=mock_emb_svc), \
             patch("app.services.embedding.service.build_embedding_index"), \
             patch("app.services.folio.owl_cache.get_owl_status", return_value={"etag": "new"}):
            result = await manager.apply()

        assert result is not None
        assert result["concepts_before"] == 100
        assert result["concepts_after"] == 105
        assert manager._status.update_available is False
        assert manager._status.last_update_at is not None
        assert manager._status.update_in_progress is False

    @pytest.mark.asyncio
    async def test_apply_prevents_concurrent(self):
        manager = OWLUpdateManager.get_instance()
        manager._status.update_in_progress = True
        result = await manager.apply()
        assert result is None

    @pytest.mark.asyncio
    async def test_apply_error_clears_in_progress(self):
        manager = OWLUpdateManager.get_instance()
        with patch("app.services.folio.owl_cache.ensure_owl_fresh", side_effect=RuntimeError("download fail")):
            result = await manager.apply()
        assert result is None
        assert manager._status.update_in_progress is False
        assert "download fail" in manager._status.error


class TestCheckAndApply:
    @pytest.mark.asyncio
    async def test_no_update_skips_apply(self):
        manager = OWLUpdateManager.get_instance()
        with patch.object(manager, "check", new_callable=AsyncMock, return_value=False):
            result = await manager.check_and_apply()
        assert result is None

    @pytest.mark.asyncio
    async def test_update_triggers_apply(self):
        manager = OWLUpdateManager.get_instance()
        stats = {"concepts_before": 50, "concepts_after": 55}
        with patch.object(manager, "check", new_callable=AsyncMock, return_value=True), \
             patch.object(manager, "apply", new_callable=AsyncMock, return_value=stats):
            result = await manager.check_and_apply()
        assert result == stats


class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_success(self):
        manager = OWLUpdateManager.get_instance()

        mock_folio_svc = MagicMock()
        mock_folio_svc._reload = MagicMock(return_value={"concepts_before": 105, "concepts_after": 100})

        mock_emb_svc = MagicMock()
        mock_emb_svc.index_folio_labels = MagicMock()

        with patch("app.services.folio.owl_cache.rollback_owl"), \
             patch("app.services.folio.folio_service.FolioService.get_instance", return_value=mock_folio_svc), \
             patch("app.services.embedding.service.EmbeddingService.get_instance", return_value=mock_emb_svc), \
             patch("app.services.embedding.service.build_embedding_index"), \
             patch("app.services.folio.owl_cache.get_owl_status", return_value={"etag": None}):
            result = await manager.rollback()

        assert result is not None
        assert result["concepts_before"] == 105
        assert result["concepts_after"] == 100
        assert manager._status.update_in_progress is False

    @pytest.mark.asyncio
    async def test_rollback_no_previous(self):
        manager = OWLUpdateManager.get_instance()
        with patch("app.services.folio.owl_cache.rollback_owl",
                    side_effect=FileNotFoundError("No previous version")):
            result = await manager.rollback()
        assert result is None
        assert manager._status.update_in_progress is False

    @pytest.mark.asyncio
    async def test_rollback_blocked_during_update(self):
        manager = OWLUpdateManager.get_instance()
        manager._status.update_in_progress = True
        result = await manager.rollback()
        assert result is None
