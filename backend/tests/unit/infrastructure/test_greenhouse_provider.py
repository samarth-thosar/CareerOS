"""Tests for GreenhouseProvider's mapping and resilience, against a stubbed HTTP client.

No network access: a fake client returns recorded-shape Greenhouse payloads, so these run in CI and stay
stable when a real board changes.
"""
from __future__ import annotations

import httpx
import pytest

from careeros.application.ports.job_source_provider import SearchCriteria
from careeros.domain.job.job import RemoteType
from careeros.infrastructure.job_sources.greenhouse_provider import GreenhouseProvider


def _job(
    job_id: int = 4567,
    title: str = "Senior Backend Engineer",
    location: str = "Remote - US",
    content: str = "&lt;p&gt;Work with Python and PostgreSQL. Base $150,000 - $190,000.&lt;/p&gt;",
) -> dict:
    return {
        "id": job_id,
        "title": title,
        "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{job_id}",
        "location": {"name": location},
        "content": content,
        "first_published": "2026-08-01T10:00:00Z",
    }


def _client_returning(routes: dict[str, dict]) -> type[httpx.AsyncClient]:
    """Build an AsyncClient subclass whose GETs are served from `routes` keyed by board token."""

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.path.split("/")[-2]
        if token not in routes:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=routes[token])

    class StubClient(httpx.AsyncClient):
        def __init__(self, **kwargs) -> None:
            kwargs.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    return StubClient


async def _collect(provider: GreenhouseProvider, criteria: SearchCriteria | None = None) -> list:
    return [posting async for posting in provider.search(criteria or SearchCriteria())]


class TestMapping:
    async def test_maps_a_job_into_a_normalized_posting(self) -> None:
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning({"acme": {"jobs": [_job()]}}))

        postings = await _collect(provider)

        assert len(postings) == 1
        posting = postings[0]
        assert posting.source_job_id == "4567"
        assert posting.title == "Senior Backend Engineer"
        assert posting.url.endswith("/4567")
        assert posting.location.remote_type is RemoteType.REMOTE
        assert posting.salary_range.minimum == 150_000
        assert "python" in posting.skills
        assert posting.posting_date is not None
        assert posting.raw_payload["id"] == 4567

    async def test_description_is_plain_text_not_escaped_html(self) -> None:
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning({"acme": {"jobs": [_job()]}}))

        posting = (await _collect(provider))[0]

        assert "&lt;" not in posting.description
        assert "<p>" not in posting.description

    async def test_falls_back_to_board_token_for_company_name(self) -> None:
        routes = {"acme-labs": {"jobs": [_job()]}}
        provider = GreenhouseProvider(["acme-labs"], client_factory=_client_returning(routes))

        assert (await _collect(provider))[0].company_name == "acme labs"

    async def test_prefers_explicit_company_name_when_present(self) -> None:
        job = _job() | {"company_name": "Acme Corporation"}
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning({"acme": {"jobs": [job]}}))

        assert (await _collect(provider))[0].company_name == "Acme Corporation"


class TestResilience:
    async def test_skips_malformed_jobs_without_failing_the_cycle(self) -> None:
        routes = {"acme": {"jobs": [{"id": None, "title": ""}, _job()]}}
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning(routes))

        assert len(await _collect(provider)) == 1

    async def test_one_unreachable_board_does_not_abort_the_others(self) -> None:
        routes = {"good": {"jobs": [_job()]}}  # "missing" 404s
        provider = GreenhouseProvider(["missing", "good"], client_factory=_client_returning(routes))

        postings = await _collect(provider)

        assert len(postings) == 1


class TestFiltering:
    async def test_keyword_filter_excludes_non_matching_titles(self) -> None:
        routes = {"acme": {"jobs": [_job(title="Account Executive", content="Sell things")]}}
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning(routes))

        assert await _collect(provider, SearchCriteria(keywords=["engineer"])) == []

    async def test_keyword_filter_matches_on_description_too(self) -> None:
        routes = {"acme": {"jobs": [_job(title="Builder", content="You will do backend engineer work")]}}
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning(routes))

        assert len(await _collect(provider, SearchCriteria(keywords=["engineer"]))) == 1

    async def test_remote_only_excludes_onsite(self) -> None:
        routes = {"acme": {"jobs": [_job(location="Bengaluru, India")]}}
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning(routes))

        assert await _collect(provider, SearchCriteria(remote_only=True)) == []

    async def test_no_keywords_keeps_everything(self) -> None:
        routes = {"acme": {"jobs": [_job(title="Chef"), _job(job_id=99, title="Engineer")]}}
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning(routes))

        assert len(await _collect(provider)) == 2

    async def test_title_keywords_ignore_description_matches(self) -> None:
        # The precision win over `keywords`: a Program Manager posting that merely mentions engineers must
        # not survive a title filter, because every kept job costs an LLM call downstream.
        routes = {
            "acme": {
                "jobs": [
                    _job(title="Program Manager", content="You will partner with backend engineers daily."),
                    _job(job_id=99, title="Backend Engineer", content="Build services."),
                ]
            }
        }
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning(routes))

        postings = await _collect(provider, SearchCriteria(title_keywords=["engineer"]))

        assert [posting.title for posting in postings] == ["Backend Engineer"]

    async def test_title_and_body_keywords_are_both_required_when_both_given(self) -> None:
        routes = {"acme": {"jobs": [_job(title="Backend Engineer", content="Java and Spring only.")]}}
        provider = GreenhouseProvider(["acme"], client_factory=_client_returning(routes))

        criteria = SearchCriteria(title_keywords=["engineer"], keywords=["python"])

        assert await _collect(provider, criteria) == []


@pytest.mark.parametrize("timestamp", ["not-a-date", None, ""])
async def test_unparseable_posting_date_becomes_none(timestamp: str | None) -> None:
    job = _job() | {"first_published": timestamp, "updated_at": timestamp}
    provider = GreenhouseProvider(["acme"], client_factory=_client_returning({"acme": {"jobs": [job]}}))

    assert (await _collect(provider))[0].posting_date is None
