"""Read-side DTOs for the job/application API.

These exist so the REST contract is a deliberate, stable shape rather than whatever the domain entities
happen to look like -- the dashboard can then be refactored independently of the domain model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class JobSummary:
    id: str
    source: str
    title: str
    company_name: str
    url: str
    location: str | None
    remote_type: str
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_is_estimated: bool
    skills: list[str]
    posting_date: datetime | None
    discovered_at: datetime
    status: str | None
    score: int | None


@dataclass(slots=True)
class ApplicationTimelineEntry:
    from_status: str | None
    to_status: str
    changed_at: datetime
    reason: str | None
    actor: str


@dataclass(slots=True)
class ApplicationSummary:
    id: str
    job_id: str
    job_title: str
    company_name: str
    job_url: str
    status: str
    applied_at: datetime | None
    score: int | None
    timeline: list[ApplicationTimelineEntry]
