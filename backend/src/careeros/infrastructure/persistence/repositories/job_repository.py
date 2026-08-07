"""SqlAlchemyJobRepository -- SQLite-backed implementation of the JobRepository port."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.domain.job.job import Job, JobSource, Location, RemoteType, SalaryRange
from careeros.infrastructure.persistence.models import JobModel


def _to_domain(model: JobModel) -> Job:
    return Job(
        id=model.id,
        source=JobSource(model.source),
        source_job_id=model.source_job_id,
        company_id=model.company_id,
        title=model.title,
        url=model.url,
        description=model.description,
        location=Location(
            city=model.location_city,
            country=model.location_country,
            remote_type=RemoteType(model.remote_type),
        ),
        salary_range=SalaryRange(
            minimum=model.salary_min,
            maximum=model.salary_max,
            currency=model.salary_currency,
            period=model.salary_period,
            is_estimated=model.salary_is_estimated,
        ),
        skills=list(model.skills),
        posting_date=model.posting_date,
        discovered_at=model.discovered_at,
        raw_payload=dict(model.raw_payload),
    )


def _to_model(job: Job) -> JobModel:
    return JobModel(
        id=job.id,
        source=job.source.value,
        source_job_id=job.source_job_id,
        company_id=job.company_id,
        title=job.title,
        url=job.url,
        description=job.description,
        location_city=job.location.city,
        location_country=job.location.country,
        remote_type=job.location.remote_type.value,
        salary_min=job.salary_range.minimum,
        salary_max=job.salary_range.maximum,
        salary_currency=job.salary_range.currency,
        salary_period=job.salary_range.period,
        salary_is_estimated=job.salary_range.is_estimated,
        skills=list(job.skills),
        posting_date=job.posting_date,
        discovered_at=job.discovered_at,
        raw_payload=dict(job.raw_payload),
    )


class SqlAlchemyJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, job_id: str) -> Job | None:
        model = await self._session.get(JobModel, job_id)
        return _to_domain(model) if model else None

    async def find_by_source(self, source: JobSource, source_job_id: str) -> Job | None:
        stmt = select(JobModel).where(JobModel.source == source.value, JobModel.source_job_id == source_job_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def add(self, job: Job) -> None:
        self._session.add(_to_model(job))

    async def save(self, job: Job) -> None:
        model = await self._session.get(JobModel, job.id)
        if model is None:
            raise ValueError(f"Job {job.id} does not exist")
        new_values = _to_model(job)
        for column in JobModel.__table__.columns.keys():
            setattr(model, column, getattr(new_values, column))
