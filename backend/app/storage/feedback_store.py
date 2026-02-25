from __future__ import annotations

import json
import logging
import tempfile
from collections import Counter
from pathlib import Path

from app.config import settings
from app.models.feedback import FeedbackEntry, InsightsSummary

logger = logging.getLogger(__name__)


class FeedbackStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.feedback_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _feedback_path(self, feedback_id: str) -> Path:
        return self.base_dir / f"{feedback_id}.json"

    async def save(self, entry: FeedbackEntry) -> None:
        path = self._feedback_path(entry.id)
        data = entry.model_dump_json(indent=2)
        fd, tmp_path = tempfile.mkstemp(dir=self.base_dir, suffix=".tmp")
        try:
            with open(fd, "w") as f:
                f.write(data)
            Path(tmp_path).rename(path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    async def load(self, feedback_id: str) -> FeedbackEntry | None:
        path = self._feedback_path(feedback_id)
        if not path.exists():
            return None
        return FeedbackEntry.model_validate_json(path.read_text())

    async def list_all(self) -> list[FeedbackEntry]:
        entries: list[FeedbackEntry] = []
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                entries.append(FeedbackEntry.model_validate_json(path.read_text()))
            except Exception:
                continue
        return entries

    async def delete(self, feedback_id: str) -> bool:
        path = self._feedback_path(feedback_id)
        if path.exists():
            path.unlink()
            return True
        return False

    async def delete_all(self) -> int:
        count = 0
        for path in list(self.base_dir.glob("*.json")):
            path.unlink()
            count += 1
        return count

    async def find_by_annotation(self, job_id: str, annotation_id: str) -> FeedbackEntry | None:
        """Find existing feedback for a specific annotation (one per annotation)."""
        for path in self.base_dir.glob("*.json"):
            try:
                entry = FeedbackEntry.model_validate_json(path.read_text())
                if entry.job_id == job_id and entry.annotation_id == annotation_id:
                    return entry
            except Exception:
                continue
        return None

    async def list_by_job(self, job_id: str) -> list[FeedbackEntry]:
        all_entries = await self.list_all()
        return [e for e in all_entries if e.job_id == job_id]

    async def get_insights(self, job_id: str | None = None) -> InsightsSummary:
        entries = await self.list_by_job(job_id) if job_id else await self.list_all()

        thumbs_up = sum(1 for e in entries if e.rating == "up")
        thumbs_down = sum(1 for e in entries if e.rating == "down")
        dismissed = sum(1 for e in entries if e.rating == "dismissed")

        # Aggregate by stage
        by_stage: dict[str, dict[str, int]] = {}
        for e in entries:
            stage_key = e.stage or "overall"
            if stage_key not in by_stage:
                by_stage[stage_key] = {"up": 0, "down": 0, "dismissed": 0}
            by_stage[stage_key][e.rating] = by_stage[stage_key].get(e.rating, 0) + 1

        # Most downvoted concepts
        down_concepts: Counter[str] = Counter()
        concept_info: dict[str, dict] = {}
        for e in entries:
            if e.rating == "down" and e.folio_label:
                down_concepts[e.folio_label] += 1
                concept_info[e.folio_label] = {
                    "folio_label": e.folio_label,
                    "folio_iri": e.folio_iri,
                }

        most_downvoted = [
            {**concept_info[label], "downvotes": count}
            for label, count in down_concepts.most_common(10)
        ]

        # Most dismissed concepts (from feedback entries with rating="dismissed")
        dismiss_concepts: Counter[str] = Counter()
        dismiss_info: dict[str, dict] = {}
        for e in entries:
            if e.rating == "dismissed" and e.folio_label:
                dismiss_concepts[e.folio_label] += 1
                dismiss_info[e.folio_label] = {
                    "folio_label": e.folio_label,
                    "folio_iri": e.folio_iri,
                }

        most_dismissed = [
            {**dismiss_info[label], "dismissals": count}
            for label, count in dismiss_concepts.most_common(10)
        ]

        # Recent feedback (last 20)
        recent = sorted(entries, key=lambda e: e.created_at, reverse=True)[:20]

        return InsightsSummary(
            total_feedback=len(entries),
            thumbs_up=thumbs_up,
            thumbs_down=thumbs_down,
            total_dismissed=dismissed,
            by_stage=by_stage,
            most_downvoted_concepts=most_downvoted,
            most_dismissed_concepts=most_dismissed,
            recent_feedback=recent,
        )
