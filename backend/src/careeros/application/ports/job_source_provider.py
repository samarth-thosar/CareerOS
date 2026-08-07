"""JobSourceProvider port -- one implementation per job board/source.

Phase-1 adapter: WellfoundProvider (Playwright). Later adapters: Greenhouse/Lever/Ashby (public APIs), a
generic career-page provider, and a LinkedIn search-only provider. See
docs/architecture/02-ports-and-interfaces.md.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class SearchCriteria:
    keywords: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    remote_only: bool = False


@dataclass(slots=True)
class RawJobPosting:
    """The untranslated shape a provider yields; infrastructure maps this into a domain Job."""

    source_job_id: str
    title: str
    company_name: str
    url: str
    description: str
    raw_payload: dict


class JobSourceProvider(Protocol):
    name: str
    supports_auto_submit: bool

    def search(self, criteria: SearchCriteria) -> AsyncIterator[RawJobPosting]: ...
