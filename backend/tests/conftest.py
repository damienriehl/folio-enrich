from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.job_store import JobStore


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the in-memory rate limiter between tests to prevent 429s."""
    from app.middleware.rate_limit import RateLimitMiddleware

    obj = getattr(app, "middleware_stack", None)
    while obj is not None:
        if isinstance(obj, RateLimitMiddleware):
            obj._requests.clear()
            break
        obj = getattr(obj, "app", None)
    yield


@pytest.fixture
def tmp_jobs_dir(tmp_path: Path) -> Path:
    return tmp_path / "jobs"


@pytest.fixture
def job_store(tmp_jobs_dir: Path) -> JobStore:
    return JobStore(base_dir=tmp_jobs_dir)


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


SAMPLE_LEGAL_TEXT = (
    "The defendant filed a Motion to Dismiss pursuant to Federal Rule of "
    "Civil Procedure 12(b)(6). The court considered the plaintiff's claims "
    "of breach of contract and negligence. After reviewing the pleadings, "
    "the court granted the motion in part and denied it in part. "
    "The breach of contract claim survived because the complaint adequately "
    "alleged the existence of a valid contract, breach by the defendant, "
    "and resulting damages. However, the negligence claim was dismissed "
    "for failure to state a claim upon which relief can be granted."
)
