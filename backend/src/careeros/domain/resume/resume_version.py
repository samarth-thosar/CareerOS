"""ResumeVersion, CoverLetter, and ResumeGapFlag -- the Resume Manager's immutable artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RenderStatus(StrEnum):
    DRAFT = "draft"
    RENDERED = "rendered"


class AlreadyRenderedError(RuntimeError):
    """Raised when `mark_rendered()` is called on an artifact that has already been rendered."""


@dataclass(slots=True)
class ResumeVersion:
    """A single tailored (or master baseline) resume snapshot.

    Immutable once rendered: `mark_rendered()` is a one-shot Draft -> Rendered transition. Any further
    tailoring is always a brand-new ResumeVersion referencing the same `job_id`, never a mutation of this
    one. The repository layer additionally refuses updates once `render_status == RENDERED`.
    """

    id: str
    source_master_version_ref: str
    content: str
    created_at: datetime
    job_id: str | None = None
    diff_summary: str | None = None
    render_status: RenderStatus = RenderStatus.DRAFT
    pdf_path: str | None = None
    has_gaps: bool = False

    def mark_rendered(self, pdf_path: str) -> None:
        if self.render_status is RenderStatus.RENDERED:
            raise AlreadyRenderedError(f"ResumeVersion {self.id} was already rendered")
        self.render_status = RenderStatus.RENDERED
        self.pdf_path = pdf_path


@dataclass(slots=True)
class CoverLetter:
    """Same immutability treatment as ResumeVersion: one-shot render, never mutated afterward."""

    id: str
    job_id: str
    resume_version_id: str
    content: str
    created_at: datetime
    render_status: RenderStatus = RenderStatus.DRAFT
    pdf_path: str | None = None

    def mark_rendered(self, pdf_path: str) -> None:
        if self.render_status is RenderStatus.RENDERED:
            raise AlreadyRenderedError(f"CoverLetter {self.id} was already rendered")
        self.render_status = RenderStatus.RENDERED
        self.pdf_path = pdf_path


class GapFlagStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(slots=True)
class ResumeGapFlag:
    """Raised instead of fabricating content.

    When tailoring needs evidence the master resume doesn't support, a gap flag is emitted for the user to
    resolve explicitly rather than inventing an achievement.
    """

    id: str
    resume_version_id: str
    job_id: str
    missing_skill_or_requirement: str
    suggested_language: str | None
    status: GapFlagStatus = GapFlagStatus.PENDING_APPROVAL
