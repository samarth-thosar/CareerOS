"""Job discovery endpoints.

Routers stay thin: resolve dependencies, call one application service or read model, return the DTO.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.application.dto.filters import JobFilters
from careeros.domain.job.location_eligibility import EligibilityRules, assess
from careeros.infrastructure.job_sources.pasted_job_extractor import PastedJobError
from careeros.infrastructure.llm.ollama_provider import LLMRequestError
from careeros.infrastructure.bootstrap import Container, in_session, search_criteria_from
from careeros.infrastructure.persistence.read_models import JobReadModel
from careeros.presentation.api.dependencies import get_container, get_session

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    ranked: Annotated[bool, Query(description="Order by score instead of discovery date")] = False,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    search: str | None = None,
    company: str | None = None,
    source: str | None = None,
    remote_type: str | None = None,
    technology: str | None = None,
    status: str | None = None,
    unscored_only: bool = False,
) -> dict[str, Any]:
    """Discovered jobs with their tracked status and latest score.

    `ranked=true` (optionally with `min_score`) is the shortlist view: best fit first, with the itemized
    reasoning behind each score attached. `matched` counts rows passing the filters, `total` counts every job,
    so the UI can say "N of M" without a second request.
    """
    filters = JobFilters(
        search=search,
        company=company,
        source=source,
        remote_type=remote_type,
        technology=technology,
        status=status,
        min_score=min_score,
        unscored_only=unscored_only,
    )
    read_model = JobReadModel(session)
    jobs = await read_model.list_jobs(
        limit=limit, offset=offset, order_by_score=ranked, filters=filters
    )
    return {
        "total": await read_model.count_jobs(),
        "matched": await read_model.count_jobs(filters),
        "scored": await read_model.count_scored(),
        "items": [asdict(job) for job in jobs],
    }


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """One job in full: the posting text plus the itemized reasoning behind its score."""
    detail = await JobReadModel(session).get_job(job_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job with id {job_id}")
    return {**asdict(detail.summary), "description": detail.description}


@router.post("/discover")
async def run_discovery(
    container: Annotated[Container, Depends(get_container)],
    provider: str | None = None,
) -> dict[str, Any]:
    """Trigger a discovery cycle now instead of waiting for the scheduler.

    Runs every enabled provider unless `provider` names one. Useful for a first run and for verifying a newly
    added board token without restarting the app. Each provider gets its own unit of work, so one failing
    source cannot roll back another's results.
    """
    criteria = search_criteria_from(container.settings)
    provider_names = [provider] if provider else [p.name for p in container.job_source_providers]

    new_jobs: dict[str, int] = {}
    for name in provider_names:
        discovered = await in_session(
            container, lambda services, n=name: services.discovery.run_cycle(n, criteria)
        )
        new_jobs[name] = len(discovered)

    return {"providers_run": provider_names, "new_jobs": new_jobs}


@router.post("/paste")
async def paste_job(
    container: Annotated[Container, Depends(get_container)],
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """Add a job by pasting its text — the route for sites CareerOS cannot and should not read automatically.

    Wellfound and LinkedIn both sit behind bot protection and forbid automated access. Copy the posting from your
    browser, paste it here with the URL, and it joins the normal pipeline: scored, tailored, cover-lettered and
    form-drafted exactly like an API-discovered job. The source is taken from the URL, so a Wellfound job is
    labelled `wellfound` rather than lumped in as "manual".
    """
    text = str(payload.get("text") or "")
    url = str(payload.get("url") or "")
    if not text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expected a 'text' field with the posting text")

    try:
        posting, source = await container.pasted_job_extractor.extract(url, text)
    except PastedJobError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    except LLMRequestError as error:
        # Actionable rather than a bare 500: the usual cause is Ollama not running or still loading the model.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Could not reach the local model to read that posting. Is Ollama running? ({error})",
        ) from error

    job, created = await in_session(container, lambda s: s.discovery.add_posting(posting, source))
    eligibility = assess(job.location.raw, EligibilityRules.from_locations(
        list(container.settings.discovery.eligible_locations)
    ))

    return {
        "job_id": job.id,
        "created": created,
        "source": source.value,
        "title": job.title,
        "company": posting.company_name,
        "location": job.location.display,
        "skills": job.skills,
        # Surfaced rather than enforced: you chose to add this, but you should know if it needs a permit you
        # don't have.
        "work_eligibility": eligibility.value,
    }
