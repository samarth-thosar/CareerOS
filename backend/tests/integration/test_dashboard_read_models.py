"""Tests for the dashboard read models: job filtering, job detail, and analytics aggregates.

Against real SQLite, because the point of these queries is the SQL -- filters composing correctly, "latest
score per job" resolving to the right row, and counts agreeing with the filtered set.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.application.dto.filters import JobFilters
from careeros.domain.application.application import Application, ApplicationStatus
from careeros.domain.company.company import Company
from careeros.domain.job.job import Job, JobSource, Location, RemoteType, SalaryRange
from careeros.domain.scoring.score import Score, ScoreBreakdown
from careeros.infrastructure.bootstrap import Container, build_container, build_repositories
from careeros.infrastructure.persistence.analytics_read_model import AnalyticsReadModel
from careeros.infrastructure.persistence.models import Base
from careeros.infrastructure.persistence.read_models import JobReadModel

DAY = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _breakdown(value: float) -> ScoreBreakdown:
    return ScoreBreakdown(
        resume_match=value,
        skill_area_fit=value,
        career_progression_fit=value,
        remote_fit=value,
        salary_fit=value,
        company_quality=value,
        narrative="Because.",
    )


def _job(job_id: str, *, company_id: str, title: str, remote: RemoteType, skills: list[str], day_offset=0) -> Job:
    return Job(
        id=job_id,
        source=JobSource.GREENHOUSE,
        source_job_id=job_id,
        company_id=company_id,
        title=title,
        url=f"https://example.com/{job_id}",
        description=f"Description for {title}.",
        location=Location(city="Berlin", country="Germany", remote_type=remote),
        salary_range=SalaryRange(minimum=None, maximum=None, currency=None, period=None),
        skills=skills,
        posting_date=None,
        discovered_at=DAY + timedelta(days=day_offset),
    )


@pytest.fixture
async def container(tmp_path, monkeypatch) -> Container:
    monkeypatch.setenv("CAREEROS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'dash.db'}")
    built = build_container()
    async with built.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield built
    finally:
        await built.engine.dispose()


@pytest.fixture
async def seeded(container: Container) -> AsyncSession:
    """Two companies, three jobs, two scored (one re-scored), one tracked application."""
    async with container.session_factory() as session:
        repos = build_repositories(session)
        await repos.companies.add(Company(id="c-acme", name="Acme"))
        await repos.companies.add(Company(id="c-globex", name="Globex"))

        await repos.jobs.add(
            _job("j-ai", company_id="c-acme", title="AI Engineer", remote=RemoteType.REMOTE,
                 skills=["python", "llm"])
        )
        await repos.jobs.add(
            _job("j-be", company_id="c-acme", title="Backend Engineer", remote=RemoteType.ONSITE,
                 skills=["python", "postgresql"], day_offset=1)
        )
        await repos.jobs.add(
            _job("j-pm", company_id="c-globex", title="Product Manager", remote=RemoteType.HYBRID,
                 skills=[], day_offset=1)
        )

        await repos.scores.add(Score(id="s-ai-old", job_id="j-ai", value=40, explanation=_breakdown(40),
                                    scoring_strategy_version="1.0.0", model_used="m", created_at=DAY))
        # Re-scored later: "current" must resolve to this row, not the 40.
        await repos.scores.add(Score(id="s-ai-new", job_id="j-ai", value=88, explanation=_breakdown(88),
                                    scoring_strategy_version="1.0.0", model_used="m",
                                    created_at=DAY + timedelta(hours=1)))
        await repos.scores.add(Score(id="s-be", job_id="j-be", value=62, explanation=_breakdown(62),
                                    scoring_strategy_version="1.0.0", model_used="m", created_at=DAY))

        application = Application.open(id="a-ai", job_id="j-ai", at=DAY)
        application.transition_to(ApplicationStatus.INTERESTED, at=DAY)
        await repos.applications.add(application)
        await session.commit()

    async with container.session_factory() as session:
        yield session


class TestRanking:
    async def test_ranked_order_uses_the_latest_score(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs(order_by_score=True)

        assert [job.id for job in jobs[:2]] == ["j-ai", "j-be"]
        assert jobs[0].score == 88, "the re-scored value must win over the original"

    async def test_unscored_jobs_sink_below_ranked_ones(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs(order_by_score=True)

        assert jobs[-1].id == "j-pm"
        assert jobs[-1].score is None

    async def test_default_order_is_newest_first(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs()

        assert jobs[0].discovered_at >= jobs[-1].discovered_at

    async def test_score_reasoning_is_attached(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs(order_by_score=True)

        assert jobs[0].score_detail is not None
        assert jobs[0].score_detail.value == 88
        assert jobs[0].score_detail.narrative == "Because."


class TestFilters:
    async def test_min_score_keeps_qualifying_jobs_and_drops_unscored_ones(self, seeded: AsyncSession) -> None:
        # j-ai scores 88 and j-be 62, so both clear 50; j-pm has no score and so has no claim to be here.
        jobs = await JobReadModel(seeded).list_jobs(filters=JobFilters(min_score=50))

        assert {job.id for job in jobs} == {"j-ai", "j-be"}

    async def test_min_score_above_every_score_returns_nothing(self, seeded: AsyncSession) -> None:
        assert await JobReadModel(seeded).list_jobs(filters=JobFilters(min_score=95)) == []

    async def test_min_score_uses_the_latest_score_not_a_superseded_one(self, seeded: AsyncSession) -> None:
        # j-ai was first scored 40 then re-scored 88; a threshold of 70 must include it.
        jobs = await JobReadModel(seeded).list_jobs(filters=JobFilters(min_score=70))

        assert {job.id for job in jobs} == {"j-ai"}

    async def test_search_matches_title_or_company(self, seeded: AsyncSession) -> None:
        read_model = JobReadModel(seeded)

        by_title = await read_model.list_jobs(filters=JobFilters(search="backend"))
        by_company = await read_model.list_jobs(filters=JobFilters(search="globex"))

        assert [job.id for job in by_title] == ["j-be"]
        assert [job.id for job in by_company] == ["j-pm"]

    async def test_technology_filter_matches_within_the_skills_array(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs(filters=JobFilters(technology="llm"))

        assert [job.id for job in jobs] == ["j-ai"]

    async def test_remote_type_filter(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs(filters=JobFilters(remote_type="remote"))

        assert [job.id for job in jobs] == ["j-ai"]

    async def test_status_filter_uses_the_tracked_application(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs(filters=JobFilters(status="interested"))

        assert [job.id for job in jobs] == ["j-ai"]

    async def test_unscored_only_returns_the_scoring_backlog(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs(filters=JobFilters(unscored_only=True))

        assert [job.id for job in jobs] == ["j-pm"]

    async def test_filters_compose(self, seeded: AsyncSession) -> None:
        jobs = await JobReadModel(seeded).list_jobs(
            filters=JobFilters(company="Acme", technology="python", remote_type="onsite")
        )

        assert [job.id for job in jobs] == ["j-be"]

    async def test_counts_reflect_the_filtered_set(self, seeded: AsyncSession) -> None:
        read_model = JobReadModel(seeded)

        assert await read_model.count_jobs() == 3
        assert await read_model.count_jobs(JobFilters(company="Acme")) == 2
        assert await read_model.count_jobs(JobFilters(min_score=80)) == 1

    async def test_no_match_returns_empty_rather_than_everything(self, seeded: AsyncSession) -> None:
        assert await JobReadModel(seeded).list_jobs(filters=JobFilters(company="Nonexistent")) == []


class TestJobDetail:
    async def test_returns_the_full_description(self, seeded: AsyncSession) -> None:
        detail = await JobReadModel(seeded).get_job("j-ai")

        assert detail is not None
        assert detail.description == "Description for AI Engineer."
        assert detail.summary.company_name == "Acme"
        assert detail.summary.score == 88

    async def test_unknown_id_returns_none(self, seeded: AsyncSession) -> None:
        assert await JobReadModel(seeded).get_job("nope") is None


class TestAnalytics:
    async def test_overview_counts(self, seeded: AsyncSession) -> None:
        overview = await AnalyticsReadModel(seeded).overview(shortlist_threshold=70)

        assert (overview.jobs_total, overview.jobs_scored, overview.jobs_unscored) == (3, 2, 1)
        assert overview.companies == 2
        assert overview.applications_by_status == {"interested": 1}

    async def test_overview_summarises_the_shortlist_from_current_scores(self, seeded: AsyncSession) -> None:
        overview = await AnalyticsReadModel(seeded).overview(shortlist_threshold=70)

        assert overview.top_score == 88, "must use the re-scored value, not the superseded 40"
        assert overview.shortlist_size == 1
        assert overview.median_score == 75  # mean of 62 and 88

    async def test_overview_on_an_empty_database(self, container: Container) -> None:
        async with container.session_factory() as session:
            overview = await AnalyticsReadModel(session).overview(shortlist_threshold=70)

        assert overview.jobs_total == 0
        assert overview.top_score is None and overview.median_score is None

    async def test_score_distribution_keeps_a_stable_axis(self, seeded: AsyncSession) -> None:
        breakdowns = await AnalyticsReadModel(seeded).breakdowns()

        assert [bucket.floor for bucket in breakdowns.score_distribution] == list(range(0, 100, 10))
        by_floor = {bucket.floor: bucket.count for bucket in breakdowns.score_distribution}
        assert by_floor[80] == 1 and by_floor[60] == 1
        assert by_floor[40] == 0, "a superseded score must not appear in the distribution"

    async def test_top_technologies_counts_across_jobs(self, seeded: AsyncSession) -> None:
        breakdowns = await AnalyticsReadModel(seeded).breakdowns()

        assert breakdowns.top_technologies[0].label == "python"
        assert breakdowns.top_technologies[0].value == 2

    async def test_top_companies_and_remote_split(self, seeded: AsyncSession) -> None:
        breakdowns = await AnalyticsReadModel(seeded).breakdowns()

        assert breakdowns.top_companies[0].label == "Acme"
        assert breakdowns.top_companies[0].value == 2
        assert {count.label for count in breakdowns.remote_split} == {"remote", "onsite", "hybrid"}

    async def test_discovery_by_day_is_chronological(self, seeded: AsyncSession) -> None:
        breakdowns = await AnalyticsReadModel(seeded).breakdowns()

        labels = [count.label for count in breakdowns.discovery_by_day]
        assert labels == sorted(labels)
        assert sum(count.value for count in breakdowns.discovery_by_day) == 3
