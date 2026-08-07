"""The Job aggregate -- an append-only record of a discovered posting."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class JobSource(StrEnum):
    WELLFOUND = "wellfound"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    GENERIC = "generic"
    LINKEDIN = "linkedin"


class RemoteType(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Location:
    city: str | None
    country: str | None
    remote_type: RemoteType


@dataclass(frozen=True, slots=True)
class SalaryRange:
    minimum: float | None
    maximum: float | None
    currency: str | None
    period: str | None
    is_estimated: bool = False


@dataclass(slots=True)
class Job:
    """A discovered job posting.

    Identity for deduplication is `(source, source_job_id)` -- rediscovering the same posting must be a
    no-op rather than a new aggregate. Raw provider payloads are kept for audit but never read directly by
    application code; a per-provider mapper in infrastructure translates them into this shape. See
    docs/architecture/01-domain-model.md.
    """

    id: str
    source: JobSource
    source_job_id: str
    company_id: str
    title: str
    url: str
    description: str
    location: Location
    salary_range: SalaryRange
    skills: list[str]
    posting_date: datetime | None
    discovered_at: datetime
    raw_payload: dict = field(default_factory=dict)

    def dedupe_key(self) -> tuple[JobSource, str]:
        return (self.source, self.source_job_id)
