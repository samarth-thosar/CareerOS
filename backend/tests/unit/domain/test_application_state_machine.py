"""Unit tests for the Application aggregate's state machine and the never-apply-twice invariant."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from careeros.domain.application.application import (
    AlreadyAppliedError,
    Application,
    ApplicationStatus,
    InvalidTransitionError,
)


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_valid_forward_transition_updates_status_and_history() -> None:
    application = Application(id="app-1", job_id="job-1")

    application.transition_to(ApplicationStatus.INTERESTED, at=_now())

    assert application.status is ApplicationStatus.INTERESTED
    assert len(application.status_history) == 1
    assert application.status_history[0].from_status is ApplicationStatus.FOUND
    assert application.status_history[0].to_status is ApplicationStatus.INTERESTED


def test_disallowed_transition_raises() -> None:
    application = Application(id="app-1", job_id="job-1")

    with pytest.raises(InvalidTransitionError):
        application.transition_to(ApplicationStatus.OFFER, at=_now())


def test_apply_requires_resume_generated_status() -> None:
    application = Application(id="app-1", job_id="job-1")

    with pytest.raises(InvalidTransitionError):
        application.apply(at=_now())


def test_apply_from_resume_generated_sets_applied_at() -> None:
    application = Application(id="app-1", job_id="job-1")
    application.transition_to(ApplicationStatus.INTERESTED, at=_now())
    application.transition_to(ApplicationStatus.RESUME_GENERATED, at=_now())

    application.apply(at=_now())

    assert application.status is ApplicationStatus.APPLIED
    assert application.applied_at is not None


def test_apply_twice_raises_even_after_later_transitions() -> None:
    application = Application(id="app-1", job_id="job-1")
    application.transition_to(ApplicationStatus.INTERESTED, at=_now())
    application.transition_to(ApplicationStatus.RESUME_GENERATED, at=_now())
    application.apply(at=_now())
    application.transition_to(ApplicationStatus.INTERVIEW, at=_now())
    application.transition_to(ApplicationStatus.REJECTED, at=_now())

    with pytest.raises(AlreadyAppliedError):
        application.apply(at=_now())
