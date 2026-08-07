"""SqlAlchemyCandidateProfileRepository -- SQLite-backed implementation of the CandidateProfileRepository port.

CandidateProfile is a single-row aggregate; `get()` returns that row once it has been created.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.domain.candidate.candidate_profile import CandidatePreferences, CandidateProfile
from careeros.infrastructure.persistence.models import CandidateProfileModel


def _to_domain(model: CandidateProfileModel) -> CandidateProfile:
    preferences = None
    if model.remote_preference is not None:
        preferences = CandidatePreferences(
            remote_preference=model.remote_preference,
            salary_floor=model.salary_floor,
            target_skill_areas=list(model.target_skill_areas),
        )
    return CandidateProfile(
        id=model.id,
        master_resume_ref=model.master_resume_ref,
        skills=list(model.skills),
        preferences=preferences,
        do_not_apply_companies=list(model.do_not_apply_companies),
        auto_apply_enabled=model.auto_apply_enabled,
        auto_tailor_resume_enabled=model.auto_tailor_resume_enabled,
    )


class SqlAlchemyCandidateProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> CandidateProfile | None:
        result = await self._session.execute(select(CandidateProfileModel).limit(1))
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def save(self, profile: CandidateProfile) -> None:
        model = await self._session.get(CandidateProfileModel, profile.id)
        if model is None:
            model = CandidateProfileModel(id=profile.id)
            self._session.add(model)
        preferences = profile.preferences
        model.master_resume_ref = profile.master_resume_ref
        model.skills = list(profile.skills)
        model.remote_preference = preferences.remote_preference if preferences else None
        model.salary_floor = preferences.salary_floor if preferences else None
        model.target_skill_areas = list(preferences.target_skill_areas) if preferences else []
        model.do_not_apply_companies = list(profile.do_not_apply_companies)
        model.auto_apply_enabled = profile.auto_apply_enabled
        model.auto_tailor_resume_enabled = profile.auto_tailor_resume_enabled
