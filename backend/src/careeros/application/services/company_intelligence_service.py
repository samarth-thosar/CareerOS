"""CompanyIntelligenceService -- builds and enriches Company profiles from Discovery/Email/Application events.

Implemented in Phase 5 (Company Intelligence).
"""
from __future__ import annotations

from careeros.application.ports.clock import Clock
from careeros.application.ports.id_generator import IdGenerator
from careeros.domain.repositories import CompanyRepository


class CompanyIntelligenceService:
    def __init__(
        self,
        company_repository: CompanyRepository,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._company_repository = company_repository
        self._clock = clock
        self._id_generator = id_generator

    async def upsert_from_job_discovered(self, company_id: str, job_id: str) -> None:
        """Record a newly seen open role against the company profile."""
        raise NotImplementedError("Company intelligence is implemented in Phase 5")
