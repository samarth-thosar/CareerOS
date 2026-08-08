"""Aggregate queries for the dashboard.

Read-side only, like the other read models: these join and count rather than rebuilding aggregates, because
reporting has no invariants to enforce and paying for aggregate reconstruction would only add latency.

Technology counts are aggregated in Python rather than SQL. `skills` is a JSON array, and unnesting it
portably would mean depending on SQLite's JSON1 extension; at single-user scale (hundreds of rows) reading the
column and counting in memory is both simpler and fast enough.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.application.dto.analytics_dto import Breakdowns, Count, Overview, ScoreBucket
from careeros.infrastructure.persistence.models import (
    ApplicationModel,
    CompanyModel,
    JobModel,
    ResumeGapFlagModel,
    ResumeVersionModel,
    ScoreModel,
)

BUCKET_WIDTH = 10


class AnalyticsReadModel:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overview(self, shortlist_threshold: int) -> Overview:
        jobs_total = await self._scalar(select(func.count()).select_from(JobModel))
        jobs_scored = await self._scalar(select(func.count(func.distinct(ScoreModel.job_id))))
        companies = await self._scalar(select(func.count()).select_from(CompanyModel))
        resume_versions = await self._scalar(select(func.count()).select_from(ResumeVersionModel))
        pending_gaps = await self._scalar(
            select(func.count())
            .select_from(ResumeGapFlagModel)
            .where(ResumeGapFlagModel.status == "pending_approval")
        )

        by_status = {
            status: count
            for status, count in (
                await self._session.execute(
                    select(ApplicationModel.status, func.count()).group_by(ApplicationModel.status)
                )
            ).all()
        }

        current = await self._current_scores()
        shortlist = [value for value in current if value >= shortlist_threshold]

        return Overview(
            jobs_total=jobs_total,
            jobs_scored=jobs_scored,
            jobs_unscored=jobs_total - jobs_scored,
            companies=companies,
            applications_by_status=by_status,
            resume_versions=resume_versions,
            pending_gaps=pending_gaps,
            shortlist_size=len(shortlist),
            shortlist_threshold=shortlist_threshold,
            top_score=max(current) if current else None,
            median_score=_median(current),
        )

    async def breakdowns(self, *, top_n: int = 8) -> Breakdowns:
        return Breakdowns(
            score_distribution=_buckets(await self._current_scores()),
            top_technologies=await self._top_technologies(top_n),
            top_companies=await self._top_companies(top_n),
            remote_split=await self._remote_split(),
            discovery_by_day=await self._discovery_by_day(),
        )

    async def _current_scores(self) -> list[int]:
        """The latest score per job. Score is append-only, so "current" means most recent by created_at."""
        latest = (
            select(ScoreModel.job_id, func.max(ScoreModel.created_at).label("latest_at"))
            .group_by(ScoreModel.job_id)
            .subquery()
        )
        stmt = select(ScoreModel.value).join(
            latest,
            (ScoreModel.job_id == latest.c.job_id) & (ScoreModel.created_at == latest.c.latest_at),
        )
        return [value for (value,) in (await self._session.execute(stmt)).all()]

    async def _top_technologies(self, top_n: int) -> list[Count]:
        rows = (await self._session.execute(select(JobModel.skills))).all()
        counter: Counter[str] = Counter()
        for (skills,) in rows:
            counter.update(skills or [])
        return [Count(label=label, value=value) for label, value in counter.most_common(top_n)]

    async def _top_companies(self, top_n: int) -> list[Count]:
        stmt = (
            select(CompanyModel.name, func.count(JobModel.id))
            .join(JobModel, JobModel.company_id == CompanyModel.id)
            .group_by(CompanyModel.name)
            .order_by(func.count(JobModel.id).desc())
            .limit(top_n)
        )
        return [Count(label=name, value=count) for name, count in (await self._session.execute(stmt)).all()]

    async def _remote_split(self) -> list[Count]:
        stmt = (
            select(JobModel.remote_type, func.count())
            .group_by(JobModel.remote_type)
            .order_by(func.count().desc())
        )
        return [
            Count(label=remote_type, value=count)
            for remote_type, count in (await self._session.execute(stmt)).all()
        ]

    async def _discovery_by_day(self) -> list[Count]:
        stmt = (
            select(func.date(JobModel.discovered_at), func.count())
            .group_by(func.date(JobModel.discovered_at))
            .order_by(func.date(JobModel.discovered_at))
        )
        return [Count(label=str(day), value=count) for day, count in (await self._session.execute(stmt)).all()]

    async def _scalar(self, stmt) -> int:
        return (await self._session.execute(stmt)).scalar_one()


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return round((ordered[middle - 1] + ordered[middle]) / 2)


def _buckets(values: list[int]) -> list[ScoreBucket]:
    """Fixed 0-100 bands, including empty ones, so the histogram's x-axis never shifts between refreshes."""
    counter = Counter(min(value // BUCKET_WIDTH * BUCKET_WIDTH, 90) for value in values)
    return [ScoreBucket(floor=floor, count=counter.get(floor, 0)) for floor in range(0, 100, BUCKET_WIDTH)]
