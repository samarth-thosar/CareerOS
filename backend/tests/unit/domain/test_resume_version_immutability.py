"""Unit tests for ResumeVersion/CoverLetter's one-shot render immutability."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from careeros.domain.resume.resume_version import AlreadyRenderedError, CoverLetter, RenderStatus, ResumeVersion


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_mark_rendered_transitions_draft_to_rendered() -> None:
    resume_version = ResumeVersion(id="rv-1", source_master_version_ref="master-1", content="...", created_at=_now())

    resume_version.mark_rendered("/tmp/resume.pdf")

    assert resume_version.render_status is RenderStatus.RENDERED
    assert resume_version.pdf_path == "/tmp/resume.pdf"


def test_mark_rendered_twice_raises() -> None:
    resume_version = ResumeVersion(id="rv-1", source_master_version_ref="master-1", content="...", created_at=_now())
    resume_version.mark_rendered("/tmp/resume.pdf")

    with pytest.raises(AlreadyRenderedError):
        resume_version.mark_rendered("/tmp/resume-v2.pdf")


def test_cover_letter_mark_rendered_twice_raises() -> None:
    cover_letter = CoverLetter(id="cl-1", job_id="job-1", resume_version_id="rv-1", content="...", created_at=_now())
    cover_letter.mark_rendered("/tmp/cover.pdf")

    with pytest.raises(AlreadyRenderedError):
        cover_letter.mark_rendered("/tmp/cover-v2.pdf")
