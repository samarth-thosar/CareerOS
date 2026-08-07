"""End-to-end test of the discovery pipeline against real SQLite and the real in-process event bus.

This is the test that proves the architecture actually connects: a provider yields a posting, and without any
direct call between them, an Application appears -- because `JobDiscovered` crossed the bus and the tracker
was subscribed in the composition root. It also exercises the real SQLAlchemy repositories, so mapping and
schema mistakes surface here rather than in production.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria
from careeros.domain.application.application import ApplicationStatus
from careeros.domain.job.job import JobSource, Location, RemoteType, SalaryRange
from careeros.infrastructure.bootstrap import (
    Container,
    build_container,
    in_session,
    register_event_handlers,
)
from careeros.infrastructure.persistence.models import Base
from careeros.infrastructure.persistence.read_models import ApplicationReadModel, JobReadModel
from tests.fakes.fake_job_source_provider import FakeJobSourceProvider


def _posting(source_job_id: str, company_name: str = "Acme", title: str = "Senior Engineer") -> RawJobPosting:
    return RawJobPosting(
        source_job_id=source_job_id,
        title=title,
        company_name=company_name,
        url=f"https://boards.greenhouse.io/acme/jobs/{source_job_id}",
        description="Build backend services in Python.",
        location=Location(city="Remote", country="US", remote_type=RemoteType.REMOTE),
        salary_range=SalaryRange(
            minimum=150_000, maximum=190_000, currency="USD", period="year", is_estimated=True
        ),
        skills=["python", "postgresql"],
        posting_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        raw_payload={"id": source_job_id},
    )


@pytest.fixture
async def container(tmp_path, monkeypatch) -> Container:
    """A real container pointed at a throwaway SQLite file, with a scripted job source."""
    monkeypatch.setenv("CAREEROS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'pipeline.db'}")
    built = build_container()
    async with built.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    built.job_source_providers = [
        FakeJobSourceProvider("greenhouse", [_posting("1"), _posting("2", title="Staff Engineer")])
    ]
    register_event_handlers(built)
    try:
        yield built
    finally:
        await built.engine.dispose()


async def _run_discovery(container: Container) -> list[str]:
    return await in_session(
        container, lambda services: services.discovery.run_cycle("greenhouse", SearchCriteria())
    )


async def _session(container: Container) -> AsyncSession:
    return container.session_factory()


class TestDiscoveryToTracking:
    async def test_every_discovered_job_is_persisted_and_tracked(self, container: Container) -> None:
        discovered = await _run_discovery(container)

        assert len(discovered) == 2
        async with await _session(container) as session:
            jobs = await JobReadModel(session).list_jobs()
            applications = await ApplicationReadModel(session).list_applications()

        assert len(jobs) == 2
        # Nothing calls the tracker directly -- these exist only because JobDiscovered crossed the event bus.
        assert len(applications) == 2
        assert {application.status for application in applications} == {ApplicationStatus.FOUND.value}

    async def test_persisted_job_round_trips_all_its_fields(self, container: Container) -> None:
        await _run_discovery(container)

        async with await _session(container) as session:
            jobs = await JobReadModel(session).list_jobs()

        job = next(job for job in jobs if job.title == "Senior Engineer")
        assert job.source == JobSource.GREENHOUSE.value
        assert job.company_name == "Acme"
        assert job.remote_type == RemoteType.REMOTE.value
        assert job.location == "Remote, US"
        assert (job.salary_min, job.salary_max, job.salary_currency) == (150_000, 190_000, "USD")
        assert job.salary_is_estimated is True
        assert job.skills == ["python", "postgresql"]

    async def test_application_timeline_starts_at_discovery(self, container: Container) -> None:
        await _run_discovery(container)

        async with await _session(container) as session:
            applications = await ApplicationReadModel(session).list_applications()

        timeline = applications[0].timeline
        assert len(timeline) == 1
        assert timeline[0].from_status is None
        assert timeline[0].to_status == ApplicationStatus.FOUND.value

    async def test_rerunning_discovery_creates_no_duplicates(self, container: Container) -> None:
        await _run_discovery(container)
        second_run = await _run_discovery(container)

        assert second_run == []
        async with await _session(container) as session:
            assert await JobReadModel(session).count_jobs() == 2
            assert await ApplicationReadModel(session).count_by_status() == {
                ApplicationStatus.FOUND.value: 2
            }

    async def test_both_jobs_at_one_company_share_a_single_company_row(self, container: Container) -> None:
        await _run_discovery(container)

        async with await _session(container) as session:
            jobs = await JobReadModel(session).list_jobs()

        assert {job.company_name for job in jobs} == {"Acme"}
