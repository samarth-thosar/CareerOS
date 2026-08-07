"""The Company aggregate, its RecruiterContact entity, and company-name normalization."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

_LEGAL_SUFFIXES = frozenset({"inc", "llc", "ltd", "limited", "corp", "corporation", "co", "gmbh", "bv", "plc"})
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def normalize_company_name(name: str) -> str:
    """Reduce a display name to a stable matching key.

    "Stripe, Inc." and "stripe" both normalize to "stripe", so the same employer discovered through two
    different job sources resolves to one Company rather than two. This is the deliberately simple first
    heuristic -- fuzzy/domain-based matching is a Company Intelligence concern (Phase 5), and lives behind
    `CompanyResolver` so it can be upgraded in one place.
    """
    tokens = [token for token in _NON_ALPHANUMERIC.split(name.lower()) if token]
    meaningful = [token for token in tokens if token not in _LEGAL_SUFFIXES]
    return " ".join(meaningful or tokens)


@dataclass(slots=True)
class TimestampedNote:
    text: str
    created_at: datetime


@dataclass(slots=True)
class RecruiterContact:
    id: str
    company_id: str
    name: str
    email: str | None = None
    linkedin: str | None = None
    role: str | None = None
    first_contacted_at: datetime | None = None
    last_contacted_at: datetime | None = None
    channel: str | None = None


@dataclass(slots=True)
class Company:
    """A durable profile that accumulates over time as Discovery, Email, and Application modules enrich it.

    `open_roles` and `response_history` are deliberately not stored here -- they are read-model queries over
    Job/Application, to avoid two sources of truth. `version` supports optimistic locking since multiple
    modules write to the same aggregate concurrently.
    """

    id: str
    name: str
    website: str | None = None
    careers_page_url: str | None = None
    linkedin_url: str | None = None
    industry: str | None = None
    funding_stage: str | None = None
    size_estimate: str | None = None
    tech_stack: list[str] = field(default_factory=list)
    engineering_blog_url: str | None = None
    notes: list[TimestampedNote] = field(default_factory=list)
    recruiter_contacts: list[RecruiterContact] = field(default_factory=list)
    version: int = 0

    def add_note(self, text: str, created_at: datetime) -> None:
        self.notes.append(TimestampedNote(text=text, created_at=created_at))

    def add_tech(self, technology: str) -> None:
        if technology not in self.tech_stack:
            self.tech_stack.append(technology)
