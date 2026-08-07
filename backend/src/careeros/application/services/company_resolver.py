"""CompanyResolver -- maps a company name seen on a job posting to exactly one Company aggregate.

Every module that encounters a company (Discovery now; Email and Company Intelligence later) resolves
through here, so the matching heuristic has a single home. Today it is normalized-name matching; richer
matching (website domain, fuzzy names) is a Phase 5 upgrade that changes this class and nothing else.
"""
from __future__ import annotations

from careeros.application.ports.id_generator import IdGenerator
from careeros.domain.company.company import Company, normalize_company_name
from careeros.domain.repositories import CompanyRepository


class CompanyResolver:
    def __init__(self, company_repository: CompanyRepository, id_generator: IdGenerator) -> None:
        self._company_repository = company_repository
        self._id_generator = id_generator

    async def resolve(self, name: str, *, website: str | None = None) -> Company:
        """Return the existing Company for `name`, creating one if this is the first time we've seen it."""
        normalized = normalize_company_name(name)
        existing = await self._company_repository.find_by_normalized_name(normalized)
        if existing is not None:
            if website and not existing.website:
                existing.website = website
                await self._company_repository.save(existing)
            return existing

        company = Company(id=self._id_generator.new_id(), name=name, website=website)
        await self._company_repository.add(company)
        return company
