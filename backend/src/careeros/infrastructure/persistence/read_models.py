"""Read-model queries for the dashboard/API.

Deliberately separate from the repositories: repositories rebuild aggregates so business rules can run
against them, whereas these queries join and flatten straight into DTOs. Reporting has no invariants to
enforce, so forcing it through aggregate reconstruction would only cost N+1 queries and latency. This is the
light CQRS split described in docs/architecture/03-event-catalog-and-pipeline.md, step 10.
"""
from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.application.dto.job_dto import (
    ApplicationSummary,
    ApplicationTimelineEntry,
    JobSummary,
    ScoreDetail,
)
from careeros.infrastructure.persistence.models import (
    ApplicationModel,
    ApplicationStatusEventModel,
    CompanyModel,
    JobModel,
    ScoreModel,
)


def _latest_score_subquery() -> Select:
    """One row per job: the most recent score, since Score is append-only."""
    return (
        select(ScoreModel.job_id, func.max(ScoreModel.created_at).label("latest_at"))
        .group_by(ScoreModel.job_id)
        .subquery()
    )


def _format_location(city: str | None, country: str | None) -> str | None:
    parts = [part for part in (city, country) if part]
    return ", ".join(parts) if parts else None


def _score_detail(score: ScoreModel | None) -> ScoreDetail | None:
    if score is None:
        return None
    return ScoreDetail(
        value=score.value,
        resume_match=score.resume_match,
        skill_area_fit=score.skill_area_fit,
        career_progression_fit=score.career_progression_fit,
        remote_fit=score.remote_fit,
        salary_fit=score.salary_fit,
        company_quality=score.company_quality,
        narrative=score.narrative,
        model_used=score.model_used,
        strategy_version=score.scoring_strategy_version,
    )


class JobReadModel:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_jobs(
        self, *, limit: int = 50, offset: int = 0, order_by_score: bool = False, min_score: int | None = None
    ) -> list[JobSummary]:
        """Discovered jobs. `order_by_score` gives the ranked shortlist; default is newest-first."""
        latest = _latest_score_subquery()
        stmt = (
            select(JobModel, CompanyModel.name, ApplicationModel.status, ScoreModel)
            .join(CompanyModel, CompanyModel.id == JobModel.company_id)
            .outerjoin(ApplicationModel, ApplicationModel.job_id == JobModel.id)
            .outerjoin(latest, latest.c.job_id == JobModel.id)
            .outerjoin(
                ScoreModel,
                (ScoreModel.job_id == latest.c.job_id) & (ScoreModel.created_at == latest.c.latest_at),
            )
        )
        if min_score is not None:
            stmt = stmt.where(ScoreModel.value >= min_score)
        # nulls_last so unscored jobs sink below the ranked ones rather than heading the shortlist.
        stmt = stmt.order_by(
            ScoreModel.value.desc().nulls_last() if order_by_score else JobModel.discovered_at.desc()
        )
        rows = (await self._session.execute(stmt.limit(limit).offset(offset))).all()
        return [
            JobSummary(
                id=job.id,
                source=job.source,
                title=job.title,
                company_name=company_name,
                url=job.url,
                location=_format_location(job.location_city, job.location_country),
                remote_type=job.remote_type,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency=job.salary_currency,
                salary_is_estimated=job.salary_is_estimated,
                skills=list(job.skills),
                posting_date=job.posting_date,
                discovered_at=job.discovered_at,
                status=status,
                score=score.value if score else None,
                score_detail=_score_detail(score),
            )
            for job, company_name, status, score in rows
        ]

    async def count_jobs(self) -> int:
        return (await self._session.execute(select(func.count()).select_from(JobModel))).scalar_one()

    async def count_scored(self) -> int:
        stmt = select(func.count(func.distinct(ScoreModel.job_id)))
        return (await self._session.execute(stmt)).scalar_one()


class ApplicationReadModel:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_applications(self, *, limit: int = 50, offset: int = 0) -> list[ApplicationSummary]:
        latest = _latest_score_subquery()
        stmt = (
            select(ApplicationModel, JobModel, CompanyModel.name, ScoreModel.value)
            .join(JobModel, JobModel.id == ApplicationModel.job_id)
            .join(CompanyModel, CompanyModel.id == JobModel.company_id)
            .outerjoin(latest, latest.c.job_id == JobModel.id)
            .outerjoin(
                ScoreModel,
                (ScoreModel.job_id == latest.c.job_id) & (ScoreModel.created_at == latest.c.latest_at),
            )
            .order_by(JobModel.discovered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).all()
        if not rows:
            return []

        timelines = await self._timelines([application.id for application, _, _, _ in rows])
        return [
            ApplicationSummary(
                id=application.id,
                job_id=application.job_id,
                job_title=job.title,
                company_name=company_name,
                job_url=job.url,
                status=application.status,
                applied_at=application.applied_at,
                score=score,
                timeline=timelines.get(application.id, []),
            )
            for application, job, company_name, score in rows
        ]

    async def _timelines(self, application_ids: list[str]) -> dict[str, list[ApplicationTimelineEntry]]:
        """Fetch history for the whole page in one query rather than one per application."""
        stmt = (
            select(ApplicationStatusEventModel)
            .where(ApplicationStatusEventModel.application_id.in_(application_ids))
            .order_by(ApplicationStatusEventModel.changed_at)
        )
        events = (await self._session.execute(stmt)).scalars().all()
        grouped: dict[str, list[ApplicationTimelineEntry]] = {}
        for event in events:
            grouped.setdefault(event.application_id, []).append(
                ApplicationTimelineEntry(
                    from_status=event.from_status,
                    to_status=event.to_status,
                    changed_at=event.changed_at,
                    reason=event.reason,
                    actor=event.actor,
                )
            )
        return grouped

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(ApplicationModel.status, func.count()).group_by(ApplicationModel.status)
        return {status: count for status, count in (await self._session.execute(stmt)).all()}
