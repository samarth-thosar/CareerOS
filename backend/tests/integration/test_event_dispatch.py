"""Integration tests for the unit-of-work / event-dispatch contract in bootstrap.in_session.

Guards the invariant that motivated DeferredEventBus: subscribers must only ever hear about committed work.
Driven through a real discovery cycle rather than by publishing directly, so these exercise the same path
production uses.
"""
from __future__ import annotations

import pytest

from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria
from careeros.domain.events import JobDiscovered
from careeros.domain.job.job import Location, RemoteType, SalaryRange
from careeros.infrastructure.bootstrap import Container, build_container, in_session
from careeros.infrastructure.persistence.models import Base
from tests.fakes.fake_job_source_provider import FakeJobSourceProvider


class Boom(RuntimeError):
    """Raised deliberately to abort a unit of work after events have been raised."""


def _posting() -> RawJobPosting:
    return RawJobPosting(
        source_job_id="1",
        title="Engineer",
        company_name="Acme",
        url="https://example.com/jobs/1",
        description="Python.",
        location=Location(city=None, country="US", remote_type=RemoteType.REMOTE),
        salary_range=SalaryRange(minimum=None, maximum=None, currency=None, period=None),
        skills=[],
        posting_date=None,
        raw_payload={},
    )


@pytest.fixture
async def container(tmp_path, monkeypatch) -> Container:
    monkeypatch.setenv("CAREEROS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'events.db'}")
    built = build_container()
    async with built.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    built.job_source_providers = [FakeJobSourceProvider("greenhouse", [_posting()])]
    try:
        yield built
    finally:
        await built.engine.dispose()


def _subscribe_recorder(container: Container) -> list[JobDiscovered]:
    received: list[JobDiscovered] = []

    async def handler(event: JobDiscovered) -> None:
        received.append(event)

    container.event_bus.subscribe(JobDiscovered, handler)
    return received


async def test_events_reach_subscribers_after_a_successful_commit(container: Container) -> None:
    received = _subscribe_recorder(container)

    await in_session(container, lambda s: s.discovery.run_cycle("greenhouse", SearchCriteria()))

    assert len(received) == 1
    assert received[0].source == "greenhouse"


async def test_events_are_discarded_when_the_unit_of_work_fails(container: Container) -> None:
    received = _subscribe_recorder(container)

    async def discover_then_fail(services) -> None:
        await services.discovery.run_cycle("greenhouse", SearchCriteria())
        raise Boom("failed after the job was persisted and the event raised")

    with pytest.raises(Boom):
        await in_session(container, discover_then_fail)

    assert received == [], "a rolled-back transaction must not announce anything"
