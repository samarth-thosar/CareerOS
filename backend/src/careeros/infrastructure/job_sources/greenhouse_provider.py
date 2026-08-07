"""GreenhouseProvider -- discovery via Greenhouse's free, unauthenticated public job-board API.

Chosen as the first real source ahead of Wellfound because it needs no scraping, no credentials, and no
rate-limit games: `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` returns structured JSON for
any company that publishes a public Greenhouse board. That covers a large share of startup engineering roles
with zero terms-of-service risk.

One board token == one company. Tokens are configured (see config/default.yaml), because Greenhouse offers no
cross-company search endpoint -- there is no global "find me all Python jobs" API to call.

`supports_auto_submit` is False: submitting means driving the hosted application form, which is a later phase.
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

_API_ROOT = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseProvider:
    name = "greenhouse"
    supports_auto_submit = False

    def __init__(
        self,
        board_tokens: list[str],
        *,
        timeout_seconds: float = 30.0,
        client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self._board_tokens = board_tokens
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory

    async def search(self, criteria: SearchCriteria) -> AsyncIterator[RawJobPosting]:
        """Yield every posting from every configured board that matches `criteria`.

        A board that fails (renamed token, transient outage) is logged and skipped -- one bad company must
        not abort the whole discovery cycle.
        """
        async with self._client_factory(timeout=self._timeout_seconds) as client:
            for board_token in self._board_tokens:
                try:
                    payload = await self._fetch_board(client, board_token)
                except (httpx.HTTPError, ValueError):
                    logger.exception("Greenhouse board %s could not be fetched; skipping", board_token)
                    continue

                for job in payload.get("jobs", []):
                    posting = self._to_posting(job, board_token)
                    if posting is not None and posting_matches(posting, criteria):
                        yield posting

    async def _fetch_board(self, client: httpx.AsyncClient, board_token: str) -> dict:
        response = await client.get(f"{_API_ROOT}/{board_token}/jobs", params={"content": "true"})
        response.raise_for_status()
        return response.json()

    def _to_posting(self, job: dict, board_token: str) -> RawJobPosting | None:
        """Map one Greenhouse job object into a normalized posting, or None if it is unusable."""
        source_job_id = job.get("id")
        title = job.get("title")
        url = job.get("absolute_url")
        if source_job_id is None or not title or not url:
            logger.warning("Skipping malformed Greenhouse job on board %s: %r", board_token, job)
            return None

        description = html_to_text(job.get("content", ""))
        searchable = f"{title}\n{description}"
        return RawJobPosting(
            source_job_id=str(source_job_id),
            title=title,
            company_name=self._company_name(job, board_token),
            url=url,
            description=description,
            location=parse_location((job.get("location") or {}).get("name")),
            salary_range=parse_salary(description),
            skills=extract_skills(searchable),
            posting_date=_parse_timestamp(job.get("first_published") or job.get("updated_at")),
            raw_payload=job,
        )

    @staticmethod
    def _company_name(job: dict, board_token: str) -> str:
        """Greenhouse rarely names the company on the job object, so fall back to the board token."""
        company = job.get("company_name")
        if isinstance(company, str) and company.strip():
            return company.strip()
        return board_token.replace("-", " ").replace("_", " ").strip()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Unparseable Greenhouse timestamp: %r", value)
        return None


