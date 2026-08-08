"""End-to-end test of the scoring half of the pipeline, against real SQLite and the real event bus.

Proves the second event hop: scoring publishes JobScored, and the tracker -- with no direct call between
them -- promotes the application to Interested when the score clears the threshold. Uses a fake LLM so the
assertions are about CareerOS's wiring rather than the model's judgment.
"""
from __future__ import annotations

import pytest

from careeros.application.dto.filters import JobFilters
from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria
from careeros.application.ports.llm_provider import LLMResponse
from careeros.domain.application.application import ApplicationStatus
from careeros.domain.job.job import Location, RemoteType, SalaryRange
from careeros.infrastructure.bootstrap import (
    Container,
    build_container,
    in_session,
    register_event_handlers,
)
from careeros.infrastructure.config.profile_loader import load_profile
from careeros.infrastructure.persistence.models import Base
from careeros.infrastructure.persistence.read_models import ApplicationReadModel, JobReadModel
from tests.fakes.fake_job_source_provider import FakeJobSourceProvider
from tests.fakes.fake_llm_provider import FakeLLMProvider


def _posting(source_job_id: str = "1") -> RawJobPosting:
    return RawJobPosting(
        source_job_id=source_job_id,
        title="Senior AI Engineer",
        company_name="Acme",
        url=f"https://example.com/jobs/{source_job_id}",
        description="Build LLM systems in Python.",
        location=Location(city=None, country="US", remote_type=RemoteType.REMOTE),
        salary_range=SalaryRange(minimum=None, maximum=None, currency=None, period=None),
        skills=["python", "llm"],
        posting_date=None,
        raw_payload={},
    )


def _llm_scoring(value: int) -> FakeLLMProvider:
    """A fake model that rates every dimension `value`, so the weighted total is also `value`."""
    dimensions = {
        "resume_match": value,
        "skill_area_fit": value,
        "career_progression_fit": value,
        "remote_fit": value,
        "salary_fit": value,
        "company_quality": value,
    }
    return FakeLLMProvider(
        LLMResponse(text="{}", parsed={**dimensions, "narrative": "Scripted."}, model_used="fake-model")
    )


@pytest.fixture
async def container(tmp_path, monkeypatch) -> Container:
    monkeypatch.setenv("CAREEROS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'scoring.db'}")
    monkeypatch.setenv("CAREEROS_TRACKER__AUTO_INTERESTED_THRESHOLD", "70")
    built = build_container()
    async with built.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    built.job_source_providers = [FakeJobSourceProvider("greenhouse", [_posting()])]
    register_event_handlers(built)
    await in_session(built, lambda s: s.candidate_profile.replace(load_profile()))
    try:
        yield built
    finally:
        await built.engine.dispose()


async def _discover(container: Container) -> str:
    job_ids = await in_session(
        container, lambda s: s.discovery.run_cycle("greenhouse", SearchCriteria())
    )
    return job_ids[0]


async def _status_of_only_application(container: Container) -> str:
    async with container.session_factory() as session:
        applications = await ApplicationReadModel(session).list_applications()
    return applications[0].status


class TestScoringPipeline:
    async def test_a_high_score_promotes_the_application_to_interested(self, container: Container) -> None:
        container.llm_provider = _llm_scoring(90)
        job_id = await _discover(container)

        await in_session(container, lambda s: s.scoring.score_job(job_id))

        # Nothing calls the tracker here; the promotion happened because JobScored crossed the event bus.
        assert await _status_of_only_application(container) == ApplicationStatus.INTERESTED.value

    async def test_a_low_score_leaves_the_application_at_found(self, container: Container) -> None:
        container.llm_provider = _llm_scoring(40)
        job_id = await _discover(container)

        await in_session(container, lambda s: s.scoring.score_job(job_id))

        # Low scores are an opinion, not a rejection: the row stays visible rather than being discarded.
        assert await _status_of_only_application(container) == ApplicationStatus.FOUND.value

    async def test_the_score_and_its_reasoning_are_readable_afterwards(self, container: Container) -> None:
        container.llm_provider = _llm_scoring(90)
        job_id = await _discover(container)

        await in_session(container, lambda s: s.scoring.score_job(job_id))

        async with container.session_factory() as session:
            jobs = await JobReadModel(session).list_jobs(order_by_score=True)

        assert jobs[0].score == 90
        assert jobs[0].score_detail is not None
        assert jobs[0].score_detail.narrative == "Scripted."
        assert jobs[0].score_detail.model_used == "fake-model"
        assert jobs[0].id == job_id


class TestScoringBacklog:
    async def test_unscored_jobs_are_the_queue_and_it_drains(self, container: Container) -> None:
        container.llm_provider = _llm_scoring(80)
        container.job_source_providers = [
            FakeJobSourceProvider("greenhouse", [_posting("1"), _posting("2"), _posting("3")])
        ]
        await in_session(container, lambda s: s.discovery.run_cycle("greenhouse", SearchCriteria()))

        first = await in_session(container, lambda s: s.scoring.score_pending(2))
        second = await in_session(container, lambda s: s.scoring.score_pending(2))

        assert (first.scored, first.remaining) == (2, 1)
        assert (second.scored, second.remaining) == (1, 0)

    async def test_already_scored_jobs_are_not_rescored(self, container: Container) -> None:
        container.llm_provider = _llm_scoring(80)
        await _discover(container)

        await in_session(container, lambda s: s.scoring.score_pending(10))
        again = await in_session(container, lambda s: s.scoring.score_pending(10))

        assert (again.scored, again.remaining) == (0, 0)

    async def test_min_score_filter_returns_only_the_shortlist(self, container: Container) -> None:
        container.llm_provider = _llm_scoring(45)
        await _discover(container)
        await in_session(container, lambda s: s.scoring.score_pending(10))

        async with container.session_factory() as session:
            shortlist = await JobReadModel(session).list_jobs(
                order_by_score=True, filters=JobFilters(min_score=70)
            )

        assert shortlist == []
