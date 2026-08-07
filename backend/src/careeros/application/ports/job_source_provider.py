"""JobSourceProvider port -- one implementation per job board/source.

Providers are the anti-corruption layer: each one owns the parsing of its own API/HTML shape and yields a
fully normalized `RawJobPosting`. `DiscoveryService` therefore stays provider-agnostic -- it never learns how
to read a Greenhouse location string or a Wellfound salary field.

Phase-1 adapters: GreenhouseProvider. Planned: Lever, Ashby, generic career pages, Wellfound. See
docs/architecture/02-ports-and-interfaces.md.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from careeros.domain.job.job import Location, SalaryRange


@dataclass(slots=True)
class SearchCriteria:
    """What to look for. Providers filter server-side where their API allows, client-side otherwise.

    Two keyword fields, because they trade off differently:

    * `title_keywords` -- must appear in the job title. High precision. Prefer this: scoring costs one LLM
      call per job, so a loose filter turns into hours of local inference on roles that were never relevant.
    * `keywords` -- may appear anywhere including the description. High recall, but nearly every engineering
      description mentions "engineer", so on its own this matches most of a board.

    When both are set a posting must satisfy both. When neither is set, everything passes.
    """

    title_keywords: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    remote_only: bool = False


@dataclass(slots=True)
class RawJobPosting:
    """A posting normalized by its provider, ready for `DiscoveryService` to persist as a domain Job.

    `raw_payload` keeps the untouched provider response for audit and for re-parsing later if a mapper
    improves -- nothing downstream reads it as a source of truth.
    """

    source_job_id: str
    title: str
    company_name: str
    url: str
    description: str
    location: Location
    salary_range: SalaryRange
    skills: list[str]
    posting_date: datetime | None
    raw_payload: dict


class JobSourceProvider(Protocol):
    name: str
    supports_auto_submit: bool

    def search(self, criteria: SearchCriteria) -> AsyncIterator[RawJobPosting]: ...
