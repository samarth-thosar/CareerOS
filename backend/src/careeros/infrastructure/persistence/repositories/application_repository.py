"""SqlAlchemyApplicationRepository -- SQLite-backed implementation of the ApplicationRepository port."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.domain.application.application import Application, ApplicationStatus, ApplicationStatusEvent
from careeros.infrastructure.persistence.models import ApplicationModel, ApplicationStatusEventModel


def _to_domain(model: ApplicationModel) -> Application:
    return Application(
        id=model.id,
        job_id=model.job_id,
        status=ApplicationStatus(model.status),
        status_history=[
            ApplicationStatusEvent(
                from_status=ApplicationStatus(event.from_status) if event.from_status else None,
                to_status=ApplicationStatus(event.to_status),
                changed_at=event.changed_at,
                reason=event.reason,
                actor=event.actor,
            )
            for event in model.status_history
        ],
        current_resume_version_id=model.current_resume_version_id,
        current_cover_letter_id=model.current_cover_letter_id,
        applied_at=model.applied_at,
        version=model.version,
    )


def _event_to_model(application_id: str, event: ApplicationStatusEvent) -> ApplicationStatusEventModel:
    return ApplicationStatusEventModel(
        application_id=application_id,
        from_status=event.from_status.value if event.from_status else None,
        to_status=event.to_status.value,
        changed_at=event.changed_at,
        reason=event.reason,
        actor=event.actor,
    )


class SqlAlchemyApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, application_id: str) -> Application | None:
        model = await self._session.get(ApplicationModel, application_id)
        return _to_domain(model) if model else None

    async def get_by_job_id(self, job_id: str) -> Application | None:
        stmt = select(ApplicationModel).where(ApplicationModel.job_id == job_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def has_ever_applied(self, job_id: str) -> bool:
        application = await self.get_by_job_id(job_id)
        return application is not None and application.applied_at is not None

    async def add(self, application: Application) -> None:
        self._session.add(
            ApplicationModel(
                id=application.id,
                job_id=application.job_id,
                status=application.status.value,
                current_resume_version_id=application.current_resume_version_id,
                current_cover_letter_id=application.current_cover_letter_id,
                applied_at=application.applied_at,
                version=application.version,
            )
        )
        for event in application.status_history:
            self._session.add(_event_to_model(application.id, event))

    async def save(self, application: Application) -> None:
        model = await self._session.get(ApplicationModel, application.id)
        if model is None:
            raise ValueError(f"Application {application.id} does not exist")
        persisted_event_count = len(model.status_history)
        model.status = application.status.value
        model.current_resume_version_id = application.current_resume_version_id
        model.current_cover_letter_id = application.current_cover_letter_id
        model.applied_at = application.applied_at
        model.version = application.version
        for event in application.status_history[persisted_event_count:]:
            self._session.add(_event_to_model(application.id, event))
