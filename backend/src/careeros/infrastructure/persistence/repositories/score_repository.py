"""SqlAlchemyScoreRepository -- SQLite-backed implementation of the ScoreRepository port."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.domain.scoring.score import Score, ScoreBreakdown
from careeros.infrastructure.persistence.models import ScoreModel


def _to_domain(model: ScoreModel) -> Score:
    return Score(
        id=model.id,
        job_id=model.job_id,
        value=model.value,
        explanation=ScoreBreakdown(
            resume_match=model.resume_match,
            skill_area_fit=model.skill_area_fit,
            career_progression_fit=model.career_progression_fit,
            remote_fit=model.remote_fit,
            salary_fit=model.salary_fit,
            company_quality=model.company_quality,
            narrative=model.narrative,
        ),
        scoring_strategy_version=model.scoring_strategy_version,
        model_used=model.model_used,
        created_at=model.created_at,
    )


class SqlAlchemyScoreRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_for_job(self, job_id: str) -> Score | None:
        stmt = (
            select(ScoreModel).where(ScoreModel.job_id == job_id).order_by(ScoreModel.created_at.desc()).limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def add(self, score: Score) -> None:
        self._session.add(
            ScoreModel(
                id=score.id,
                job_id=score.job_id,
                value=score.value,
                resume_match=score.explanation.resume_match,
                skill_area_fit=score.explanation.skill_area_fit,
                career_progression_fit=score.explanation.career_progression_fit,
                remote_fit=score.explanation.remote_fit,
                salary_fit=score.explanation.salary_fit,
                company_quality=score.explanation.company_quality,
                narrative=score.explanation.narrative,
                scoring_strategy_version=score.scoring_strategy_version,
                model_used=score.model_used,
                created_at=score.created_at,
            )
        )
