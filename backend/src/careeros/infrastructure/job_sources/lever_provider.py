"""LeverProvider -- discovery via Lever's free, unauthenticated postings API.

`api.lever.co/v0/postings/{company}?mode=json` returns structured JSON for any company with a public Lever
board. Like Greenhouse there is no cross-company search, so companies are named in config.

Chosen over Wellfound, which the candidate asked about first: Wellfound sits behind Cloudflare bot protection
(a filtered listing URL returns 403, and even the pages that load block on a second request), publishes no API,
gates most listings behind a login, and forbids scraping in its terms. Lever and Ashby give the same kind of
startup postings through documented endpoints with none of that.

Lever's shape differs from Greenhouse's in three ways worth knowing: the title lives in `text`, the location in
`categories.location`, and the description arrives as `descriptionPlain` alongside an HTML variant.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

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

_API_ROOT = "https://api.lever.co/v0/postings"


class LeverProvider:
    name = "lever"
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
                    response = await client.get(f"{_API_ROOT}/{slug}", params={"mode": "json"})
                    response.raise_for_status()
                    postings = response.json()
                except (httpx.HTTPError, ValueError):
                    logger.exception("Lever board %s could not be fetched; skipping", slug)
                    continue

                if not isinstance(postings, list):
                    logger.warning("Unexpected Lever payload for %s", slug)
                    continue

                for raw in postings:
                    posting = self._to_posting(raw, slug)
                    if posting is not None and posting_matches(posting, criteria):
                        yield posting

    def _to_posting(self, raw: dict, slug: str) -> RawJobPosting | None:
        source_job_id = raw.get("id")
        title = raw.get("text")
        url = raw.get("hostedUrl") or raw.get("applyUrl")
        if not source_job_id or not title or not url:
            logger.warning("Skipping malformed Lever posting on %s: %r", slug, raw)
            return None

        categories = raw.get("categories") or {}
        # descriptionPlain avoids a second HTML strip; fall back to the HTML field when it is absent.
        description = raw.get("descriptionPlain") or html_to_text(raw.get("description", ""))
        searchable = f"{title}\n{description}"

        return RawJobPosting(
            source_job_id=str(source_job_id),
            title=title,
            company_name=_company_name(raw, slug),
            url=url,
            description=description,
            location=parse_location(categories.get("location")),
            salary_range=parse_salary(description),
            skills=extract_skills(searchable),
            posting_date=_from_epoch_millis(raw.get("createdAt")),
            raw_payload=raw,
        )


def _company_name(raw: dict, slug: str) -> str:
    """Lever rarely names the company on a posting, so fall back to the board slug."""
    for key in ("company", "companyName"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return slug.replace("-", " ").replace("_", " ").strip()


def _from_epoch_millis(value: object) -> datetime | None:
    """Lever timestamps are epoch milliseconds, unlike Greenhouse's ISO strings."""
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        logger.debug("Unusable Lever timestamp: %r", value)
        return None
