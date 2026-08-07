"""Tests for DiscoveryService: de-duplication, company resolution, and event publication."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria
from careeros.application.services.company_resolver import CompanyResolver
from careeros.application.services.discovery_service import DiscoveryService, UnknownProviderError
from careeros.domain.events import JobDiscovered
from careeros.domain.job.job import JobSource, Location, RemoteType, SalaryRange
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_job_source_provider import FakeJobSourceProvider
from tests.fakes.in_memory_company_repository import InMemoryCompanyRepository
from tests.fakes.in_memory_event_bus import InMemoryEventBus
from tests.fakes.in_memory_job_repository import InMemoryJobRepository
from tests.fakes.sequential_id_generator import SequentialIdGenerator

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _posting(source_job_id: str = "1", company_name: str = "Acme", title: str = "Engineer") -> RawJobPosting:
    return RawJobPosting(
        source_job_id=source_job_id,
        title=title,
        company_name=company_name,
        url=f"https://example.com/jobs/{source_job_id}",
        description="Build things with Python.",
        location=Location(city=None, country="US", remote_type=RemoteType.REMOTE),
        salary_range=SalaryRange(minimum=None, maximum=None, currency=None, period=None),
        skills=["python"],
        posting_date=None,
        raw_payload={"id": source_job_id},
    )


def _build(postings: list[RawJobPosting]) -> tuple[DiscoveryService, InMemoryJobRepository, InMemoryEventBus]:
    jobs = InMemoryJobRepository()
    companies = InMemoryCompanyRepository()
    bus = InMemoryEventBus()
    ids = SequentialIdGenerator()
    service = DiscoveryService(
        providers=[FakeJobSourceProvider("greenhouse", postings)],
        job_repository=jobs,
        company_resolver=CompanyResolver(company_repository=companies, id_generator=ids),
        event_bus=bus,
        clock=FakeClock(NOW),
        id_generator=ids,
    )
    return service, jobs, bus


class TestRunCycle:
    async def test_persists_new_jobs_and_publishes_one_event_each(self) -> None:
        service, jobs, bus = _build([_posting("1"), _posting("2")])

        discovered = await service.run_cycle("greenhouse", SearchCriteria())

        assert len(discovered) == 2
        assert len(bus.published) == 2
        assert all(isinstance(event, JobDiscovered) for event in bus.published)
        assert await jobs.find_by_source(JobSource.GREENHOUSE, "1") is not None

    async def test_stamps_discovered_at_from_the_clock(self) -> None:
        service, jobs, _ = _build([_posting("1")])

        await service.run_cycle("greenhouse", SearchCriteria())

        job = await jobs.find_by_source(JobSource.GREENHOUSE, "1")
        assert job is not None and job.discovered_at == NOW

    async def test_rediscovering_a_posting_is_a_no_op(self) -> None:
        service, _, bus = _build([_posting("1")])

        first = await service.run_cycle("greenhouse", SearchCriteria())
        second = await service.run_cycle("greenhouse", SearchCriteria())

        assert len(first) == 1
        assert second == []
        assert len(bus.published) == 1, "a re-seen job must not re-announce itself"

    async def test_duplicate_within_one_cycle_is_persisted_once(self) -> None:
        # The same posting can surface twice in a cycle when a company is watched under two board tokens.
        service, _, bus = _build([_posting("1"), _posting("1")])

        discovered = await service.run_cycle("greenhouse", SearchCriteria())

        assert len(discovered) == 1
        assert len(bus.published) == 1

    async def test_unknown_provider_raises(self) -> None:
        service, _, _ = _build([])

        with pytest.raises(UnknownProviderError):
            await service.run_cycle("wellfound", SearchCriteria())

    async def test_criteria_are_passed_through_to_the_provider(self) -> None:
        provider = FakeJobSourceProvider("greenhouse", [])
        ids = SequentialIdGenerator()
        service = DiscoveryService(
            providers=[provider],
            job_repository=InMemoryJobRepository(),
            company_resolver=CompanyResolver(InMemoryCompanyRepository(), ids),
            event_bus=InMemoryEventBus(),
            clock=FakeClock(NOW),
            id_generator=ids,
        )
        criteria = SearchCriteria(keywords=["llm"], remote_only=True)

        await service.run_cycle("greenhouse", criteria)

        assert provider.received_criteria == [criteria]


class TestCompanyResolution:
    async def test_two_jobs_at_one_company_share_a_company_id(self) -> None:
        service, jobs, _ = _build([_posting("1", company_name="Acme"), _posting("2", company_name="Acme")])

        await service.run_cycle("greenhouse", SearchCriteria())

        first = await jobs.find_by_source(JobSource.GREENHOUSE, "1")
        second = await jobs.find_by_source(JobSource.GREENHOUSE, "2")
        assert first is not None and second is not None
        assert first.company_id == second.company_id

    async def test_name_variants_resolve_to_the_same_company(self) -> None:
        service, jobs, _ = _build(
            [_posting("1", company_name="Acme, Inc."), _posting("2", company_name="acme")]
        )

        await service.run_cycle("greenhouse", SearchCriteria())

        first = await jobs.find_by_source(JobSource.GREENHOUSE, "1")
        second = await jobs.find_by_source(JobSource.GREENHOUSE, "2")
        assert first is not None and second is not None
        assert first.company_id == second.company_id

    async def test_different_companies_get_different_ids(self) -> None:
        service, jobs, _ = _build([_posting("1", company_name="Acme"), _posting("2", company_name="Globex")])

        await service.run_cycle("greenhouse", SearchCriteria())

        first = await jobs.find_by_source(JobSource.GREENHOUSE, "1")
        second = await jobs.find_by_source(JobSource.GREENHOUSE, "2")
        assert first is not None and second is not None
        assert first.company_id != second.company_id
