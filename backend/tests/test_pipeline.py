import asyncio
from pathlib import Path

import pytest

from app.models.document import DocumentFormat, DocumentInput
from app.models.job import Job, JobStatus
from app.pipeline.orchestrator import PipelineOrchestrator
from app.storage.job_store import JobStore


@pytest.fixture
def pipeline(tmp_path: Path) -> PipelineOrchestrator:
    store = JobStore(base_dir=tmp_path / "jobs")
    return PipelineOrchestrator(store)


class TestPipelineOrchestrator:
    @pytest.mark.asyncio
    async def test_plain_text_pipeline(self, pipeline: PipelineOrchestrator):
        job = Job(input=DocumentInput(content="The court granted the motion."))
        result = await pipeline.run(job)

        assert result.status == JobStatus.COMPLETED
        assert result.result.canonical_text is not None
        assert result.result.canonical_text.full_text == "The court granted the motion."
        assert len(result.result.canonical_text.chunks) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_persists_job(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")
        pipeline = PipelineOrchestrator(store)
        job = Job(input=DocumentInput(content="Test content."))
        await pipeline.run(job)

        loaded = await store.load(job.id)
        assert loaded is not None
        assert loaded.status == JobStatus.COMPLETED
        assert loaded.result.canonical_text is not None

    @pytest.mark.asyncio
    async def test_pipeline_handles_errors(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")
        pipeline = PipelineOrchestrator(store)
        # No input — stages that depend on it will warn and skip
        job = Job(input=None)
        result = await pipeline.run(job)

        # Pipeline completes (stage errors are non-fatal)
        assert result.status == JobStatus.COMPLETED


class TestJobStore:
    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")
        job = Job(input=DocumentInput(content="test"))
        await store.save(job)

        loaded = await store.load(job.id)
        assert loaded is not None
        assert loaded.id == job.id
        assert loaded.input.content == "test"

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")
        from uuid import uuid4
        result = await store.load(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_list_jobs(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")
        job1 = Job(input=DocumentInput(content="one"))
        job2 = Job(input=DocumentInput(content="two"))
        await store.save(job1)
        await store.save(job2)

        jobs = await store.list_jobs()
        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_delete_job(self, tmp_path: Path):
        store = JobStore(base_dir=tmp_path / "jobs")
        job = Job(input=DocumentInput(content="test"))
        await store.save(job)
        assert await store.delete(job.id)
        assert await store.load(job.id) is None


class TestAPIEndpoints:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_create_enrichment(self, client):
        resp = await client.post(
            "/enrich",
            json={"content": "The court ruled on the motion.", "format": "plain_text"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_enrichment(self, client):
        # Create a job
        resp = await client.post(
            "/enrich",
            json={"content": "Test legal text.", "format": "plain_text"},
        )
        job_id = resp.json()["job_id"]

        # Wait briefly for background task
        await asyncio.sleep(0.5)

        # Get the job
        resp = await client.get(f"/enrich/{job_id}")
        assert resp.status_code == 200
        job = resp.json()
        assert job["id"] == job_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_job(self, client):
        from uuid import uuid4
        resp = await client.get(f"/enrich/{uuid4()}")
        assert resp.status_code == 404
