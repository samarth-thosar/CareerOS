"""InMemoryJobRepository -- test fake for JobRepository, backed by a plain dict."""
from __future__ import annotations

from careeros.domain.job.job import Job, JobSource


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

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
