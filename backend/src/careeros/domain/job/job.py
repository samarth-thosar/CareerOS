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
    """Where a job is.

    `raw` is the posting's own location text, kept verbatim and treated as the source of truth. `city` and
    `country` are a convenience for display and are only populated when the text names a single unambiguous
    place -- postings routinely list several ("New York, San Francisco, Seattle, or Remote (US/Canada)"), and
    forcing those into one city/country pair produced nonsense. Anything deciding eligibility must read `raw`.
    """

    city: str | None
    country: str | None
    remote_type: RemoteType
    raw: str | None = None

    @property
    def display(self) -> str:
        """What to show a human: the posting's own words, falling back to the parsed pair."""
        if self.raw:
            return self.raw
        parts = [part for part in (self.city, self.country) if part]
        return ", ".join(parts) if parts else "unspecified"


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
