"""Tests for job retention and concurrency limits."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.document import DocumentInput
from app.models.job import Job, JobStatus
from app.storage.job_store import JobStore


class TestJobRetention:
    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_old_jobs(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")

        # Create an old job (40 days ago)
        old_job = Job(input=DocumentInput(content="old"))
        old_job.status = JobStatus.COMPLETED
        old_job.updated_at = datetime.now(timezone.utc) - timedelta(days=40)
        await store.save(old_job)

        # Create a recent job
        new_job = Job(input=DocumentInput(content="new"))
        new_job.status = JobStatus.COMPLETED
        await store.save(new_job)

        deleted = await store.cleanup_expired(retention_days=30)
        assert deleted == 1

        # Old job should be gone, new job should remain
        assert await store.load(old_job.id) is None
        assert await store.load(new_job.id) is not None

    @pytest.mark.asyncio
    async def test_cleanup_expired_no_old_jobs(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")

        job = Job(input=DocumentInput(content="recent"))
        await store.save(job)

        deleted = await store.cleanup_expired(retention_days=30)
        assert deleted == 0


class TestConcurrencyLimits:
    @pytest.mark.asyncio
    async def test_count_active_empty(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")
        assert await store.count_active() == 0

    @pytest.mark.asyncio
    async def test_count_active_with_in_progress(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")

        job1 = Job(input=DocumentInput(content="a"))
        job1.status = JobStatus.IDENTIFYING
        await store.save(job1)

        job2 = Job(input=DocumentInput(content="b"))
        job2.status = JobStatus.COMPLETED
        await store.save(job2)

        job3 = Job(input=DocumentInput(content="c"))
        job3.status = JobStatus.RESOLVING
        await store.save(job3)

        assert await store.count_active() == 2  # job1 and job3

    @pytest.mark.asyncio
    async def test_count_active_excludes_completed_failed_pending(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")

        for status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PENDING):
            job = Job(input=DocumentInput(content="x"))
            job.status = status
            await store.save(job)

        assert await store.count_active() == 0
