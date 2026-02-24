"""Smart OWL cache with freshness check and version rollback.

Manages the FOLIO OWL file cached by folio-python, adding:
- ETag-based freshness checks (HEAD request per startup)
- XML validation before overwriting the cache
- One-version rollback via {hash}.owl.previous
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
from lxml import etree

logger = logging.getLogger(__name__)

# Mirror the folio-python library defaults
_REPO_OWNER = "alea-institute"
_REPO_NAME = "FOLIO"
_REPO_BRANCH = "2.0.0"
_CACHE_DIR = Path.home() / ".folio" / "cache"
_OWL_URL = (
    f"https://raw.githubusercontent.com/{_REPO_OWNER}/{_REPO_NAME}"
    f"/{_REPO_BRANCH}/FOLIO.owl"
)

# Compute the same blake2b hash that folio-python uses for the cache filename
_CACHE_KEY = f"{_REPO_OWNER}/{_REPO_NAME}/{_REPO_BRANCH}"
_CACHE_HASH = hashlib.blake2b(_CACHE_KEY.encode()).hexdigest()
_CACHE_FILE = _CACHE_DIR / "github" / f"{_CACHE_HASH}.owl"
_PREVIOUS_FILE = _CACHE_FILE.with_suffix(".owl.previous")
_METADATA_FILE = _CACHE_DIR / "github" / f"{_CACHE_HASH}.metadata.json"

_REQUEST_TIMEOUT = 30.0


def _load_metadata() -> dict:
    """Load metadata JSON, returning empty dict if missing or corrupt."""
    if not _METADATA_FILE.exists():
        return {}
    try:
        return json.loads(_METADATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_metadata(data: dict) -> None:
    """Write metadata JSON atomically."""
    _METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _METADATA_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.rename(_METADATA_FILE)


def ensure_owl_fresh() -> None:
    """Check if the cached FOLIO OWL is up to date; download if stale.

    Uses HTTP conditional requests (ETag / If-None-Match) to avoid
    re-downloading the full ~18 MB file when nothing has changed.
    """
    meta = _load_metadata()
    stored_etag = meta.get("etag")

    # Step 1: HEAD request with conditional header
    headers: dict[str, str] = {}
    if stored_etag and _CACHE_FILE.exists():
        headers["If-None-Match"] = stored_etag

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
            head_resp = client.head(_OWL_URL, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("OWL freshness check failed (network error): %s", exc)
        return

    if head_resp.status_code == 304:
        logger.info("FOLIO OWL is up to date (304 Not Modified)")
        meta["checked_at"] = datetime.now(timezone.utc).isoformat()
        _save_metadata(meta)
        return

    if head_resp.status_code != 200:
        logger.warning(
            "OWL freshness HEAD returned unexpected status %d", head_resp.status_code
        )
        return

    new_etag = head_resp.headers.get("etag", "").strip('"')

    # Step 2: Download the full OWL
    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
            get_resp = client.get(_OWL_URL)
            get_resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("OWL download failed: %s", exc)
        return

    content = get_resp.content

    # Step 3: Validate XML
    try:
        etree.fromstring(content)
    except etree.XMLSyntaxError as exc:
        logger.error(
            "Downloaded OWL failed XML validation — keeping previous version: %s", exc
        )
        return

    # Step 4: Rotate and write
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if _CACHE_FILE.exists():
        # Keep one-version backup
        if _PREVIOUS_FILE.exists():
            _PREVIOUS_FILE.unlink()
        _CACHE_FILE.rename(_PREVIOUS_FILE)

    tmp = _CACHE_FILE.with_suffix(".owl.tmp")
    tmp.write_bytes(content)
    tmp.rename(_CACHE_FILE)

    # Step 5: Update metadata
    _save_metadata({
        "etag": new_etag,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "owl_bytes": len(content),
    })

    logger.info(
        "FOLIO OWL updated (etag: %s, %d bytes)", new_etag, len(content)
    )


def rollback_owl() -> None:
    """Roll back to the previous OWL version.

    Raises FileNotFoundError if no previous version is available.
    """
    if not _PREVIOUS_FILE.exists():
        raise FileNotFoundError("No previous OWL version available for rollback")

    failed = _CACHE_FILE.with_suffix(".owl.failed")

    if _CACHE_FILE.exists():
        _CACHE_FILE.rename(failed)

    _PREVIOUS_FILE.rename(_CACHE_FILE)

    if failed.exists():
        failed.unlink()

    # Clear etag so next startup re-checks freshness
    meta = _load_metadata()
    meta.pop("etag", None)
    meta["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
    _save_metadata(meta)

    logger.info("Rolled back to previous FOLIO OWL version")


def get_owl_status() -> dict:
    """Return cache status for the health endpoint."""
    meta = _load_metadata()
    return {
        "cached": _CACHE_FILE.exists(),
        "etag": meta.get("etag"),
        "checked_at": meta.get("checked_at"),
        "owl_bytes": meta.get("owl_bytes"),
        "has_previous_version": _PREVIOUS_FILE.exists(),
    }
