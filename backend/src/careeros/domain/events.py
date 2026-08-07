"""Domain event definitions.

Events are immutable, data-only records of meaningful aggregate-state transitions. Each carries a common
envelope (id, type, timestamp, correlation id) plus a small, ID-carrying payload -- see
docs/architecture/03-event-catalog-and-pipeline.md for the full catalog, granularity rationale, and the
publisher/subscriber map. Services publish these through the `EventBus` port; the events themselves have no
behavior beyond holding data.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base envelope shared by every domain event."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=_utcnow)
    correlation_id: str | None = None

    @property
    def event_type(self) -> str:
        return type(self).__name__


@dataclass(frozen=True, kw_only=True)
class JobDiscovered(DomainEvent):
    job_id: str
    company_id: str
    source: str
    url: str


@dataclass(frozen=True, kw_only=True)
class JobScored(DomainEvent):
    job_id: str
    score_id: str
    value: int
    scoring_strategy_version: str


@dataclass(frozen=True, kw_only=True)
class ApplicationStatusChanged(DomainEvent):
    application_id: str
    job_id: str
    from_status: str
    to_status: str
    reason: str | None = None
    actor: str = "system"


@dataclass(frozen=True, kw_only=True)
class ResumeTailoringRequested(DomainEvent):
    application_id: str
    job_id: str
    trigger: str


@dataclass(frozen=True, kw_only=True)
class ResumeGenerated(DomainEvent):
    resume_version_id: str
    job_id: str
    application_id: str
    has_gaps: bool


@dataclass(frozen=True, kw_only=True)
class ResumeGapFlagged(DomainEvent):
    gap_flag_id: str
    resume_version_id: str
    missing_item: str


@dataclass(frozen=True, kw_only=True)
class CoverLetterGenerated(DomainEvent):
    cover_letter_id: str
    job_id: str
    resume_version_id: str


@dataclass(frozen=True, kw_only=True)
class ApplicationReadyToApply(DomainEvent):
    application_id: str
    job_id: str
    score: int


@dataclass(frozen=True, kw_only=True)
class InboundCommandReceived(DomainEvent):
    command_id: str
    intent: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ApplicationSubmitted(DomainEvent):
    application_id: str
    job_id: str
    method: str
    confirmation_ref: str | None = None


@dataclass(frozen=True, kw_only=True)
class RecruiterEmailDetected(DomainEvent):
    email_message_id: str
    classification: str
    confidence: float
    linked_company_id: str | None = None
    linked_application_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class MemoryInsightsUpdated(DomainEvent):
    insight_type: str
    payload: dict[str, Any] = field(default_factory=dict)
