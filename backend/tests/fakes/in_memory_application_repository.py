"""InMemoryApplicationRepository -- test fake enforcing the same one-Application-per-job rule as the DB."""
from __future__ import annotations

from careeros.domain.application.application import Application


class DuplicateApplicationError(RuntimeError):
    """Stands in for the real unique constraint on Application.job_id."""


class InMemoryApplicationRepository:
    def __init__(self) -> None:
        self._applications: dict[str, Application] = {}

    async def get_by_id(self, application_id: str) -> Application | None:
        return self._applications.get(application_id)

    async def get_by_job_id(self, job_id: str) -> Application | None:
        return next((a for a in self._applications.values() if a.job_id == job_id), None)

    async def has_ever_applied(self, job_id: str) -> bool:
        application = await self.get_by_job_id(job_id)
        return application is not None and application.applied_at is not None

    async def add(self, application: Application) -> None:
        if await self.get_by_job_id(application.job_id) is not None:
            raise DuplicateApplicationError(f"Job {application.job_id} already has an application")
        self._applications[application.id] = application

    async def save(self, application: Application) -> None:
        self._applications[application.id] = application
