"""Job discovery endpoints.

Routers stay thin: resolve dependencies, call one application service or read model, return the DTO.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

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
) -> dict[str, Any]:
    """Discovered jobs with their tracked status and latest score.

    `ranked=true` (optionally with `min_score`) is the shortlist view: best fit first, with the itemized
    reasoning behind each score attached.
    """
    read_model = JobReadModel(session)
    jobs = await read_model.list_jobs(
        limit=limit, offset=offset, order_by_score=ranked, min_score=min_score
    )
    return {
        "total": await read_model.count_jobs(),
        "scored": await read_model.count_scored(),
        "items": [asdict(job) for job in jobs],
    }


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
