"""The Application aggregate -- the central lifecycle object -- and its state machine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ApplicationStatus(StrEnum):
    FOUND = "found"
    INTERESTED = "interested"
    SAVED = "saved"
    RESUME_GENERATED = "resume_generated"
    APPLIED = "applied"
    INTERVIEW = "interview"
    ASSESSMENT = "assessment"
    RECRUITER_CONTACT = "recruiter_contact"
    REJECTED = "rejected"
    OFFER = "offer"
    ARCHIVED = "archived"


# Rejected and Archived are reachable from nearly every non-terminal state; everything else follows the
# documented forward lifecycle. See docs/architecture/01-domain-model.md for the diagram.
_ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.FOUND: frozenset(
        {ApplicationStatus.INTERESTED, ApplicationStatus.SAVED, ApplicationStatus.REJECTED, ApplicationStatus.ARCHIVED}
    ),
    ApplicationStatus.INTERESTED: frozenset(
        {ApplicationStatus.SAVED, ApplicationStatus.RESUME_GENERATED, ApplicationStatus.REJECTED, ApplicationStatus.ARCHIVED}
    ),
    ApplicationStatus.SAVED: frozenset(
        {ApplicationStatus.RESUME_GENERATED, ApplicationStatus.REJECTED, ApplicationStatus.ARCHIVED}
    ),
    ApplicationStatus.RESUME_GENERATED: frozenset(
        {ApplicationStatus.APPLIED, ApplicationStatus.REJECTED, ApplicationStatus.ARCHIVED}
    ),
    ApplicationStatus.APPLIED: frozenset(
        {
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.ASSESSMENT,
            ApplicationStatus.RECRUITER_CONTACT,
            ApplicationStatus.REJECTED,
            ApplicationStatus.OFFER,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.INTERVIEW: frozenset(
        {
            ApplicationStatus.ASSESSMENT,
            ApplicationStatus.RECRUITER_CONTACT,
            ApplicationStatus.REJECTED,
            ApplicationStatus.OFFER,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.ASSESSMENT: frozenset(
        {
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.RECRUITER_CONTACT,
            ApplicationStatus.REJECTED,
            ApplicationStatus.OFFER,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.RECRUITER_CONTACT: frozenset(
        {
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.ASSESSMENT,
            ApplicationStatus.REJECTED,
            ApplicationStatus.OFFER,
            ApplicationStatus.ARCHIVED,
        }
    ),
    ApplicationStatus.REJECTED: frozenset({ApplicationStatus.ARCHIVED}),
    ApplicationStatus.OFFER: frozenset({ApplicationStatus.ARCHIVED}),
    ApplicationStatus.ARCHIVED: frozenset(),
}


class InvalidTransitionError(ValueError):
    """Raised when an Application status transition isn't allowed by the state machine."""


class AlreadyAppliedError(RuntimeError):
    """Raised when `apply()` is called on an Application that has already been submitted.

    The check is unconditional on `applied_at`, not on current status, because status can move
    Applied -> Interview -> Rejected and must still never allow a second submission.
    """


@dataclass(slots=True)
class ApplicationStatusEvent:
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    changed_at: datetime
    reason: str | None = None
    actor: str = "system"


@dataclass(slots=True)
class Application:
    """The application lifecycle aggregate for a single Job.

    `job_id` is unique per Application at the persistence layer, giving a structural 1:1 with Job as the
    second layer of the "never apply twice" defense; this class provides the primary layer via `apply()`.
    See docs/architecture/01-domain-model.md.
    """

    id: str
    job_id: str
    status: ApplicationStatus = ApplicationStatus.FOUND
    status_history: list[ApplicationStatusEvent] = field(default_factory=list)
    current_resume_version_id: str | None = None
    current_cover_letter_id: str | None = None
    applied_at: datetime | None = None
    version: int = 0

    @classmethod
    def open(cls, *, id: str, job_id: str, at: datetime) -> "Application":
        """Start tracking a newly discovered job, seeding the timeline with the Found state.

        Every Application begins here, so its history always explains itself from discovery onward rather
        than starting at whatever the first transition happened to be.
        """
        application = cls(id=id, job_id=job_id)
        application.status_history.append(
            ApplicationStatusEvent(from_status=None, to_status=ApplicationStatus.FOUND, changed_at=at)
        )
        return application

    def transition_to(
        self,
        new_status: ApplicationStatus,
        *,
        at: datetime,
        reason: str | None = None,
        actor: str = "system",
    ) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.status]
        if new_status not in allowed:
            raise InvalidTransitionError(f"Cannot transition from {self.status} to {new_status}")
        self.status_history.append(
            ApplicationStatusEvent(
                from_status=self.status, to_status=new_status, changed_at=at, reason=reason, actor=actor
            )
        )
        self.status = new_status

    def apply(self, *, at: datetime) -> None:
        """Record submission. Raises `AlreadyAppliedError` if this Application has ever been applied to."""
        if self.applied_at is not None:
            raise AlreadyAppliedError(f"Application {self.id} was already applied to at {self.applied_at}")
        self.transition_to(ApplicationStatus.APPLIED, at=at)
        self.applied_at = at
