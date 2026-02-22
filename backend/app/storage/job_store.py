from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from app.config import settings
from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)


class JobStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.jobs_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _job_path(self, job_id: UUID) -> Path:
        return self.base_dir / f"{job_id}.json"

    async def save(self, job: Job) -> None:
        path = self._job_path(job.id)
        data = job.model_dump_json(indent=2)
        # Atomic write: write to temp file then rename
        fd, tmp_path = tempfile.mkstemp(dir=self.base_dir, suffix=".tmp")
        try:
            with open(fd, "w") as f:
                f.write(data)
            Path(tmp_path).rename(path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    async def load(self, job_id: UUID) -> Job | None:
        path = self._job_path(job_id)
        if not path.exists():
            return None
        data = path.read_text()
        return Job.model_validate_json(data)

    async def list_jobs(self) -> list[Job]:
        jobs = []
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                jobs.append(Job.model_validate_json(path.read_text()))
            except Exception:
                continue
        return jobs

    async def delete(self, job_id: UUID) -> bool:
        path = self._job_path(job_id)
        if path.exists():
            path.unlink()
            return True
        return False

    async def count_active(self) -> int:
        """Count jobs currently in progress."""
        count = 0
        for path in self.base_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                status = data.get("status", "")
                if status not in ("completed", "failed", "pending"):
                    count += 1
            except Exception:
                continue
        return count

    async def cleanup_expired(self, retention_days: int | None = None) -> int:
        """Delete jobs older than retention period. Returns count of deleted jobs."""
        if retention_days is None:
            retention_days = settings.job_retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        deleted = 0

        for path in list(self.base_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                updated = data.get("updated_at") or data.get("created_at")
                if updated:
                    ts = datetime.fromisoformat(updated)
                    if ts < cutoff:
                        path.unlink()
                        deleted += 1
            except Exception:
                continue

        return deleted
