"""Tests for POST /concepts/batch endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _make_mock_detail(iri_hash: str, label: str):
    """Create a mock ConceptDetail-like object with model_dump()."""
    detail = MagicMock()
    detail.model_dump.return_value = {
        "iri_hash": iri_hash,
        "label": label,
        "branch": "Area of Law",
    }
    return detail


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


_LOOKUP_PATH = "app.services.folio.concept_detail.lookup_concept_detail"
_FOLIO_PATH = "app.api.routes.concepts._get_folio"


@pytest.mark.anyio
async def test_batch_returns_found_concepts(client):
    """Valid hashes return their details; unknown hashes are omitted."""
    def fake_lookup(folio, iri_hash):
        if iri_hash == "KNOWN1":
            return _make_mock_detail("KNOWN1", "Contract Law")
        if iri_hash == "KNOWN2":
            return _make_mock_detail("KNOWN2", "Tort Law")
        return None

    with (
        patch(_FOLIO_PATH, return_value=MagicMock()),
        patch(_LOOKUP_PATH, side_effect=fake_lookup),
    ):
        resp = await client.post("/concepts/batch", json={
            "iri_hashes": ["KNOWN1", "UNKNOWN", "KNOWN2"],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert "KNOWN1" in data
    assert "KNOWN2" in data
    assert "UNKNOWN" not in data
    assert data["KNOWN1"]["label"] == "Contract Law"


@pytest.mark.anyio
async def test_batch_empty_list(client):
    """Empty list returns empty dict."""
    with (
        patch(_FOLIO_PATH, return_value=MagicMock()),
        patch(_LOOKUP_PATH, return_value=None),
    ):
        resp = await client.post("/concepts/batch", json={"iri_hashes": []})

    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.anyio
async def test_batch_caps_at_100(client):
    """Request with >100 hashes is rejected by validation."""
    hashes = [f"HASH{i}" for i in range(101)]

    with (
        patch(_FOLIO_PATH, return_value=MagicMock()),
        patch(_LOOKUP_PATH, return_value=None),
    ):
        resp = await client.post("/concepts/batch", json={"iri_hashes": hashes})

    assert resp.status_code == 422  # Pydantic validation error


@pytest.mark.anyio
async def test_batch_all_unknown(client):
    """All unknown hashes returns empty dict."""
    with (
        patch(_FOLIO_PATH, return_value=MagicMock()),
        patch(_LOOKUP_PATH, return_value=None),
    ):
        resp = await client.post("/concepts/batch", json={
            "iri_hashes": ["UNKNOWN1", "UNKNOWN2"],
        })

    assert resp.status_code == 200
    assert resp.json() == {}
