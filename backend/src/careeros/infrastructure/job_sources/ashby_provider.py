"""AshbyProvider -- discovery via Ashby's free, unauthenticated job-board API.

`api.ashbyhq.com/posting-api/job-board/{company}` returns `{"jobs": [...]}` for any company with a public Ashby
board. Same trade as Greenhouse and Lever: no cross-company search, so companies are named in config.

Ashby's shape is the friendliest of the three -- `title`, `location` and `descriptionPlain` are all top level --
but it does expose `isListed`, and an unlisted posting is one the company has taken down. Those are skipped:
surfacing a job that can no longer be applied to wastes a scoring call and a slot on the shortlist.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime

import httpx

from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria
from careeros.infrastructure.job_sources.filtering import posting_matches
from careeros.infrastructure.job_sources.text_extraction import (
    extract_skills,
    html_to_text,
    parse_location,
    parse_salary,
)

logger = logging.getLogger(__name__)

_API_ROOT = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyProvider:
    name = "ashby"
    supports_auto_submit = False

    def __init__(
        self,
        company_slugs: list[str],
        *,
        timeout_seconds: float = 30.0,
        client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self._company_slugs = company_slugs
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory

    async def search(self, criteria: SearchCriteria) -> AsyncIterator[RawJobPosting]:
        async with self._client_factory(timeout=self._timeout_seconds) as client:
            for slug in self._company_slugs:
                try:
                    response = await client.get(f"{_API_ROOT}/{slug}")
                    response.raise_for_status()
                    jobs = response.json().get("jobs", [])
                except (httpx.HTTPError, ValueError, AttributeError):
                    logger.exception("Ashby board %s could not be fetched; skipping", slug)
                    continue

                for raw in jobs:
                    posting = self._to_posting(raw, slug)
                    if posting is not None and posting_matches(posting, criteria):
                        yield posting

    def _to_posting(self, raw: dict, slug: str) -> RawJobPosting | None:
        source_job_id = raw.get("id")
        title = raw.get("title")
        url = raw.get("jobUrl") or raw.get("applyUrl")
        if not source_job_id or not title or not url:
            logger.warning("Skipping malformed Ashby posting on %s: %r", slug, raw)
            return None

        # isListed=False means the company has withdrawn the posting; applying is no longer possible.
        if raw.get("isListed") is False:
            return None

        description = raw.get("descriptionPlain") or html_to_text(raw.get("descriptionHtml", ""))
        searchable = f"{title}\n{description}"

        return RawJobPosting(
            source_job_id=str(source_job_id),
            title=title,
            company_name=_company_name(raw, slug),
            url=url,
            description=description,
            location=parse_location(raw.get("location")),
            salary_range=parse_salary(description),
            skills=extract_skills(searchable),
            posting_date=_parse_iso(raw.get("publishedAt") or raw.get("updatedAt")),
            raw_payload=raw,
        )


def _company_name(raw: dict, slug: str) -> str:
    value = raw.get("organizationName")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return slug.replace("-", " ").replace("_", " ").strip()


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Unparseable Ashby timestamp: %r", value)
        return None
