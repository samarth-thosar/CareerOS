"""CandidateProfileService -- reads and replaces the single CandidateProfile row.

Exists so seeding from config and serving the profile to the dashboard are use cases with a home, rather than
callers reaching for the repository directly. Later phases (Memory suggesting preference changes, the resume
manager recording a master-resume ref) extend this service instead of widening access to persistence.
"""
from __future__ import annotations

import logging

from careeros.domain.candidate.candidate_profile import CandidateProfile
from careeros.domain.repositories import CandidateProfileRepository

logger = logging.getLogger(__name__)


class CandidateProfileService:
    def __init__(self, candidate_profile_repository: CandidateProfileRepository) -> None:
        self._candidate_profile_repository = candidate_profile_repository

    async def get(self) -> CandidateProfile | None:
        return await self._candidate_profile_repository.get()

    async def replace(self, profile: CandidateProfile) -> CandidateProfile:
        """Overwrite the stored profile. Used by config seeding, which is always an explicit action."""
        await self._candidate_profile_repository.save(profile)
        logger.info("Candidate profile replaced (%d role interests)", len(profile.role_interests))
        return profile
