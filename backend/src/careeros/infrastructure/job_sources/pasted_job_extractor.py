"""Turns text the candidate pasted into a normalized RawJobPosting.

This is the escape hatch for sites that cannot be read programmatically and should not be. Wellfound sits behind
Cloudflare bot protection and forbids automated access; LinkedIn is the same. Rather than circumventing either,
the candidate browses there themselves, copies the posting, and pastes it -- the reading is human, and everything
downstream (scoring, tailoring, cover letters, form drafting) treats the result exactly like an API-discovered
job.

Shaped as a normaliser rather than a service method on purpose: it belongs beside the Greenhouse, Lever and Ashby
providers because it does the same job they do -- own the parsing of one input shape and emit a `RawJobPosting`.
That keeps `DiscoveryService` free of any knowledge of how postings are read, and keeps the parsing helpers
(which are infrastructure) out of the application layer.
"""
from __future__ import annotations

import logging

from careeros.application.ports.job_source_provider import RawJobPosting
from careeros.application.ports.llm_provider import LLMProvider
from careeros.application.prompts.job_extraction_prompt import build_job_extraction_prompt
from careeros.domain.job.job import JobSource
from careeros.infrastructure.job_sources.text_extraction import (
    extract_skills,
    parse_location,
    parse_salary,
)

logger = logging.getLogger(__name__)

# Domains mapped to the source they represent, so a pasted job records where it genuinely came from rather than a
# generic "manual" label -- the candidate asked to always see a job's origin, and "Wellfound" versus "a company
# career page" changes how a posting should be read.
_DOMAIN_SOURCES: tuple[tuple[str, JobSource], ...] = (
    ("wellfound.com", JobSource.WELLFOUND),
    ("angel.co", JobSource.WELLFOUND),
    ("linkedin.com", JobSource.LINKEDIN),
    ("greenhouse.io", JobSource.GREENHOUSE),
    ("lever.co", JobSource.LEVER),
    ("ashbyhq.com", JobSource.ASHBY),
)


class PastedJobError(ValueError):
    """Raised when the pasted text does not contain a readable job posting."""


def source_for_url(url: str) -> JobSource:
    """Infer the source from the posting URL, falling back to GENERIC for company career pages."""
    lowered = (url or "").lower()
    for domain, source in _DOMAIN_SOURCES:
        if domain in lowered:
            return source
    return JobSource.GENERIC


class PastedJobExtractor:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    async def extract(self, url: str, pasted_text: str) -> tuple[RawJobPosting, JobSource]:
        if not pasted_text.strip():
            raise PastedJobError("Nothing to extract: the pasted text is empty")

        response = await self._llm_provider.complete(build_job_extraction_prompt(pasted_text))
        if response.parsed is None:
            raise PastedJobError("Could not read a job out of that text")

        fields = response.parsed
        title = str(fields.get("title") or "").strip()
        company_name = str(fields.get("company_name") or "").strip()
        if not title or not company_name:
            raise PastedJobError("The text did not contain a recognisable job title and company")

        description = str(fields.get("description") or "").strip() or pasted_text.strip()
        salary_source = "\n".join([str(fields.get("salary_text") or ""), description])

        # A pasted job has no provider id, so the URL identifies it -- which also makes re-pasting the same
        # posting a no-op rather than a duplicate.
        source_job_id = url.strip() or f"pasted:{company_name}:{title}"

        posting = RawJobPosting(
            source_job_id=source_job_id,
            title=title,
            company_name=company_name,
            url=url.strip() or "(pasted, no URL)",
            description=description,
            location=parse_location(str(fields.get("location") or "").strip() or None),
            salary_range=parse_salary(salary_source),
            skills=extract_skills("\n".join([title, description])),
            posting_date=None,
            # The original paste is kept so a later, better extractor can re-read it without asking again.
            raw_payload={"pasted_text": pasted_text[:20_000], "extracted": fields},
        )
        logger.info("Extracted pasted job: %s at %s", title, company_name)
        return posting, source_for_url(url)
