"""InMemoryCompanyRepository -- test fake for CompanyRepository, keyed the same way the real one is."""
from __future__ import annotations

from careeros.domain.company.company import Company, normalize_company_name


class InMemoryCompanyRepository:
    def __init__(self) -> None:
        self._companies: dict[str, Company] = {}

    async def get_by_id(self, company_id: str) -> Company | None:
        return self._companies.get(company_id)

    async def find_by_website(self, website: str) -> Company | None:
        return next((c for c in self._companies.values() if c.website == website), None)

    async def find_by_normalized_name(self, normalized_name: str) -> Company | None:
        return next(
            (c for c in self._companies.values() if normalize_company_name(c.name) == normalized_name), None
        )

    async def add(self, company: Company) -> None:
        self._companies[company.id] = company

    async def save(self, company: Company) -> None:
        self._companies[company.id] = company
