"""SqlAlchemyCompanyRepository -- SQLite-backed implementation of the CompanyRepository port."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.domain.company.company import (
    Company,
    RecruiterContact,
    TimestampedNote,
    normalize_company_name,
)
from careeros.infrastructure.persistence.models import CompanyModel, RecruiterContactModel


def _contact_to_domain(model: RecruiterContactModel) -> RecruiterContact:
    return RecruiterContact(
        id=model.id,
        company_id=model.company_id,
        name=model.name,
        email=model.email,
        linkedin=model.linkedin,
        role=model.role,
        first_contacted_at=model.first_contacted_at,
        last_contacted_at=model.last_contacted_at,
        channel=model.channel,
    )


def _contact_to_model(contact: RecruiterContact) -> RecruiterContactModel:
    return RecruiterContactModel(
        id=contact.id,
        company_id=contact.company_id,
        name=contact.name,
        email=contact.email,
        linkedin=contact.linkedin,
        role=contact.role,
        first_contacted_at=contact.first_contacted_at,
        last_contacted_at=contact.last_contacted_at,
        channel=contact.channel,
    )


def _notes_to_json(notes: list[TimestampedNote]) -> list[dict]:
    return [{"text": note.text, "created_at": note.created_at.isoformat()} for note in notes]


def _notes_from_json(raw_notes: list[dict]) -> list[TimestampedNote]:
    return [
        TimestampedNote(text=note["text"], created_at=datetime.fromisoformat(note["created_at"]))
        for note in raw_notes
    ]


def _to_domain(model: CompanyModel, contacts: list[RecruiterContactModel]) -> Company:
    return Company(
        id=model.id,
        name=model.name,
        website=model.website,
        careers_page_url=model.careers_page_url,
        linkedin_url=model.linkedin_url,
        industry=model.industry,
        funding_stage=model.funding_stage,
        size_estimate=model.size_estimate,
        tech_stack=list(model.tech_stack),
        engineering_blog_url=model.engineering_blog_url,
        notes=_notes_from_json(model.notes),
        recruiter_contacts=[_contact_to_domain(contact) for contact in contacts],
        version=model.version,
    )


class SqlAlchemyCompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: str) -> Company | None:
        model = await self._session.get(CompanyModel, company_id)
        if model is None:
            return None
        return _to_domain(model, await self._get_contacts(company_id))

    async def find_by_website(self, website: str) -> Company | None:
        stmt = select(CompanyModel).where(CompanyModel.website == website)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return _to_domain(model, await self._get_contacts(model.id))

    async def find_by_normalized_name(self, normalized_name: str) -> Company | None:
        stmt = select(CompanyModel).where(CompanyModel.normalized_name == normalized_name)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return _to_domain(model, await self._get_contacts(model.id))

    async def add(self, company: Company) -> None:
        self._session.add(
            CompanyModel(
                id=company.id,
                name=company.name,
                normalized_name=normalize_company_name(company.name),
                website=company.website,
                careers_page_url=company.careers_page_url,
                linkedin_url=company.linkedin_url,
                industry=company.industry,
                funding_stage=company.funding_stage,
                size_estimate=company.size_estimate,
                tech_stack=list(company.tech_stack),
                engineering_blog_url=company.engineering_blog_url,
                notes=_notes_to_json(company.notes),
                version=company.version,
            )
        )
        for contact in company.recruiter_contacts:
            self._session.add(_contact_to_model(contact))

    async def save(self, company: Company) -> None:
        model = await self._session.get(CompanyModel, company.id)
        if model is None:
            raise ValueError(f"Company {company.id} does not exist")
        model.name = company.name
        model.normalized_name = normalize_company_name(company.name)
        model.website = company.website
        model.careers_page_url = company.careers_page_url
        model.linkedin_url = company.linkedin_url
        model.industry = company.industry
        model.funding_stage = company.funding_stage
        model.size_estimate = company.size_estimate
        model.tech_stack = list(company.tech_stack)
        model.engineering_blog_url = company.engineering_blog_url
        model.notes = _notes_to_json(company.notes)
        model.version = company.version

    async def _get_contacts(self, company_id: str) -> list[RecruiterContactModel]:
        stmt = select(RecruiterContactModel).where(RecruiterContactModel.company_id == company_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
