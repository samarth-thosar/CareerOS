"""InMemoryJobRepository -- test fake for JobRepository, backed by a plain dict.

`find_unscored`/`count_unscored` need to know which jobs have scores, exactly as the real repository does via
a join against the scores table. Passing the score repository in mirrors that relationship rather than
maintaining a second, divergent notion of "scored".
"""
from __future__ import annotations

from careeros.domain.job.job import Job, JobSource
from tests.fakes.in_memory_score_repository import InMemoryScoreRepository


class InMemoryJobRepository:
    def __init__(self, score_repository: InMemoryScoreRepository | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._scores = score_repository

    async def get_by_id(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def find_by_source(self, source: JobSource, source_job_id: str) -> Job | None:
        for job in self._jobs.values():
            if job.source == source and job.source_job_id == source_job_id:
                return job
        return None

    async def add(self, job: Job) -> None:
        self._jobs[job.id] = job

    async def save(self, job: Job) -> None:
        self._jobs[job.id] = job

    async def find_unscored(self, limit: int) -> list[Job]:
        return self._unscored()[:limit]

    async def count_unscored(self) -> int:
        return len(self._unscored())

    def _unscored(self) -> list[Job]:
        scored_job_ids = {score.job_id for score in self._scores.scores} if self._scores else set()
        pending = [job for job in self._jobs.values() if job.id not in scored_job_ids]
        return sorted(pending, key=lambda job: job.discovered_at)
