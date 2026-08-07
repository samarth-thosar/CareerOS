"""SqlAlchemyResumeRepository -- SQLite-backed implementation of the ResumeRepository port.

Enforces ResumeVersion/CoverLetter immutability at the persistence boundary: `save_resume_version` refuses
to update a row once its `render_status` is `RENDERED`, matching the domain's one-shot `mark_rendered()`
guarantee. See docs/architecture/01-domain-model.md.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.domain.resume.resume_version import (
    CoverLetter,
    GapFlagStatus,
    RenderStatus,
    ResumeGapFlag,
    ResumeVersion,
)
from careeros.infrastructure.persistence.models import (
    CoverLetterModel,
    ResumeGapFlagModel,
    ResumeVersionModel,
)


def _resume_to_domain(model: ResumeVersionModel) -> ResumeVersion:
    return ResumeVersion(
        id=model.id,
        source_master_version_ref=model.source_master_version_ref,
        content=model.content,
        created_at=model.created_at,
        job_id=model.job_id,
        diff_summary=model.diff_summary,
        render_status=RenderStatus(model.render_status),
        pdf_path=model.pdf_path,
        has_gaps=model.has_gaps,
    )


def _cover_letter_to_domain(model: CoverLetterModel) -> CoverLetter:
    return CoverLetter(
        id=model.id,
        job_id=model.job_id,
        resume_version_id=model.resume_version_id,
        content=model.content,
        created_at=model.created_at,
        render_status=RenderStatus(model.render_status),
        pdf_path=model.pdf_path,
    )


class SqlAlchemyResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_resume_version(self, resume_version_id: str) -> ResumeVersion | None:
        model = await self._session.get(ResumeVersionModel, resume_version_id)
        return _resume_to_domain(model) if model else None

    async def add_resume_version(self, resume_version: ResumeVersion) -> None:
        self._session.add(
            ResumeVersionModel(
                id=resume_version.id,
                source_master_version_ref=resume_version.source_master_version_ref,
                job_id=resume_version.job_id,
                content=resume_version.content,
                diff_summary=resume_version.diff_summary,
                render_status=resume_version.render_status.value,
                pdf_path=resume_version.pdf_path,
                has_gaps=resume_version.has_gaps,
                created_at=resume_version.created_at,
            )
        )

    async def save_resume_version(self, resume_version: ResumeVersion) -> None:
        model = await self._session.get(ResumeVersionModel, resume_version.id)
        if model is None:
            raise ValueError(f"ResumeVersion {resume_version.id} does not exist")
        if model.render_status == RenderStatus.RENDERED.value:
            raise ValueError(f"ResumeVersion {resume_version.id} is rendered and cannot be updated")
        model.content = resume_version.content
        model.diff_summary = resume_version.diff_summary
        model.render_status = resume_version.render_status.value
        model.pdf_path = resume_version.pdf_path
        model.has_gaps = resume_version.has_gaps

    async def list_versions_for_job(self, job_id: str) -> list[ResumeVersion]:
        """Every version generated for a job, newest first -- nothing is ever replaced, only added to."""
        stmt = (
            select(ResumeVersionModel)
            .where(ResumeVersionModel.job_id == job_id)
            .order_by(ResumeVersionModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [_resume_to_domain(model) for model in result.scalars().all()]

    async def add_gap_flag(self, gap_flag: ResumeGapFlag) -> None:
        self._session.add(
            ResumeGapFlagModel(
                id=gap_flag.id,
                resume_version_id=gap_flag.resume_version_id,
                job_id=gap_flag.job_id,
                missing_skill_or_requirement=gap_flag.missing_skill_or_requirement,
                suggested_language=gap_flag.suggested_language,
                status=gap_flag.status.value,
            )
        )

    async def list_pending_gap_flags(self) -> list[ResumeGapFlag]:
        stmt = select(ResumeGapFlagModel).where(
            ResumeGapFlagModel.status == GapFlagStatus.PENDING_APPROVAL.value
        )
        result = await self._session.execute(stmt)
        return [
            ResumeGapFlag(
                id=model.id,
                resume_version_id=model.resume_version_id,
                job_id=model.job_id,
                missing_skill_or_requirement=model.missing_skill_or_requirement,
                suggested_language=model.suggested_language,
                status=GapFlagStatus(model.status),
            )
            for model in result.scalars().all()
        ]

    async def get_cover_letter(self, cover_letter_id: str) -> CoverLetter | None:
        model = await self._session.get(CoverLetterModel, cover_letter_id)
        return _cover_letter_to_domain(model) if model else None

    async def add_cover_letter(self, cover_letter: CoverLetter) -> None:
        self._session.add(
            CoverLetterModel(
                id=cover_letter.id,
                job_id=cover_letter.job_id,
                resume_version_id=cover_letter.resume_version_id,
                content=cover_letter.content,
                render_status=cover_letter.render_status.value,
                pdf_path=cover_letter.pdf_path,
                created_at=cover_letter.created_at,
            )
        )
