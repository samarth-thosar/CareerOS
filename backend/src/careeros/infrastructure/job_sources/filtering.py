"""Shared `SearchCriteria` filtering for job-source providers.

Lives here rather than inside a provider because every source needs the identical rule, and none of the ATS
APIs (Greenhouse, Lever, Ashby) accept keyword parameters -- filtering is always client-side. Keeping one
implementation means adding a provider cannot quietly introduce different matching semantics.
"""
from __future__ import annotations

from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria
from careeros.domain.job.job import RemoteType
from careeros.domain.job.location_eligibility import is_worth_keeping
from careeros.infrastructure.job_sources.text_extraction import matches_keyword


def posting_matches(posting: RawJobPosting, criteria: SearchCriteria) -> bool:
    """Whether a posting satisfies every constraint set on `criteria`.

    Unset constraints are not applied, so an empty `SearchCriteria` keeps everything.
    """
    # Work authorisation first: it is a hard constraint, and checking it before anything else means an
    # ineligible posting never reaches the database or costs an LLM call to score.
    if criteria.eligibility is not None and not is_worth_keeping(posting.location.raw, criteria.eligibility):
        return False

    if criteria.remote_only and posting.location.remote_type is not RemoteType.REMOTE:
        return False

    if criteria.title_keywords and not any(
        matches_keyword(posting.title, keyword) for keyword in criteria.title_keywords
    ):
        return False

    if criteria.keywords:
        haystack = f"{posting.title}\n{posting.description}"
        if not any(matches_keyword(haystack, keyword) for keyword in criteria.keywords):
            return False

    return True
