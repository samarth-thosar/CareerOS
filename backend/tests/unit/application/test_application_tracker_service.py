"""Tests for ApplicationTrackerService -- tracking on discovery, idempotency, and score promotion."""
from __future__ import annotations

from datetime import datetime, timezone

from careeros.application.services.application_tracker_service import ApplicationTrackerService
from careeros.domain.application.application import ApplicationStatus
from careeros.domain.events import ApplicationStatusChanged
from tests.fakes.fake_clock import FakeClock
from tests.fakes.in_memory_application_repository import InMemoryApplicationRepository
from tests.fakes.in_memory_event_bus import InMemoryEventBus
from tests.fakes.sequential_id_generator import SequentialIdGenerator

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _build(threshold: int = 70) -> tuple[ApplicationTrackerService, InMemoryApplicationRepository, InMemoryEventBus]:
    repository = InMemoryApplicationRepository()
    bus = InMemoryEventBus()
    service = ApplicationTrackerService(
        application_repository=repository,
        event_bus=bus,
        clock=FakeClock(NOW),
        id_generator=SequentialIdGenerator("app"),
        auto_interested_threshold=threshold,
    )
    return service, repository, bus


class TestTrackDiscoveredJob:
    async def test_creates_an_application_at_found_with_seeded_history(self) -> None:
        service, repository, _ = _build()

        application = await service.track_discovered_job("job-1")

        assert application.status is ApplicationStatus.FOUND
        assert await repository.get_by_job_id("job-1") is not None
        assert len(application.status_history) == 1
        assert application.status_history[0].from_status is None
        assert application.status_history[0].to_status is ApplicationStatus.FOUND
        assert application.status_history[0].changed_at == NOW

    async def test_is_idempotent_when_the_same_event_is_replayed(self) -> None:
        # Handlers run in their own transaction, so a redelivered event must not create a second row.
        service, _, _ = _build()

        first = await service.track_discovered_job("job-1")
        second = await service.track_discovered_job("job-1")

        assert first.id == second.id
        assert len(first.status_history) == 1

    async def test_distinct_jobs_get_distinct_applications(self) -> None:
        service, _, _ = _build()

        first = await service.track_discovered_job("job-1")
        second = await service.track_discovered_job("job-2")

        assert first.id != second.id


class TestApplyScore:
    async def test_promotes_to_interested_when_threshold_is_met(self) -> None:
        service, repository, bus = _build(threshold=70)
        await service.track_discovered_job("job-1")

        await service.apply_score("job-1", 85)

        application = await repository.get_by_job_id("job-1")
        assert application is not None
        assert application.status is ApplicationStatus.INTERESTED
        assert any(isinstance(event, ApplicationStatusChanged) for event in bus.published)

    async def test_boundary_score_equal_to_threshold_promotes(self) -> None:
        service, repository, _ = _build(threshold=70)
        await service.track_discovered_job("job-1")

        await service.apply_score("job-1", 70)

        application = await repository.get_by_job_id("job-1")
        assert application is not None and application.status is ApplicationStatus.INTERESTED

    async def test_low_score_stays_at_found_rather_than_being_rejected(self) -> None:
        service, repository, bus = _build(threshold=70)
        await service.track_discovered_job("job-1")

        await service.apply_score("job-1", 40)

        application = await repository.get_by_job_id("job-1")
        assert application is not None
        assert application.status is ApplicationStatus.FOUND
        assert bus.published == []

    async def test_does_not_regress_an_application_already_past_found(self) -> None:
        service, repository, bus = _build(threshold=70)
        application = await service.track_discovered_job("job-1")
        application.transition_to(ApplicationStatus.INTERESTED, at=NOW)
        await repository.save(application)
        bus.published.clear()

        await service.apply_score("job-1", 95)

        assert bus.published == [], "re-scoring an in-flight application must not re-announce a transition"

    async def test_scoring_an_untracked_job_is_ignored(self) -> None:
        service, _, bus = _build()

        await service.apply_score("job-unknown", 95)

        assert bus.published == []
