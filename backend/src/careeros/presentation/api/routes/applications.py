"""Application tracking endpoints -- the durable record of every job CareerOS has acted on."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.application.services.application_submission_service import AnswersIncompleteError
from careeros.infrastructure.bootstrap import Container, in_session
from careeros.infrastructure.persistence.read_models import ApplicationReadModel
from careeros.presentation.api.dependencies import get_container, get_session

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("")
async def list_applications(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Every tracked application with its full status timeline."""
    read_model = ApplicationReadModel(session)
    applications = await read_model.list_applications(limit=limit, offset=offset)
    return {
        "counts_by_status": await read_model.count_by_status(),
        "items": [asdict(application) for application in applications],
    }


@router.post("/submit")
async def submit_selected(
    container: Annotated[Container, Depends(get_container)],
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """Apply to the jobs the user picked.

    The selection is always explicit: CareerOS never chooses which jobs to apply to. Returns 409 when required
    application answers are still placeholders, because submitting an invented notice period or salary to a real
    employer is worse than not applying.
    """
    job_ids = payload.get("job_ids")
    if not isinstance(job_ids, list) or not job_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expected a non-empty 'job_ids' list")

    try:
        result = await in_session(container, lambda s: s.submission.submit_selected([str(j) for j in job_ids]))
    except AnswersIncompleteError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    return {
        "counts": result.counts,
        "submitted": [asdict(item) for item in result.submitted],
        "skipped": [asdict(item) for item in result.skipped],
    }


@router.post("/{job_id}/confirm-applied")
async def confirm_applied(
    job_id: str,
    container: Annotated[Container, Depends(get_container)],
) -> dict[str, Any]:
    """Record that the user submitted a form themselves.

    Most ATS forms cannot be automated yet, and an application that happened but was never recorded breaks both
    the never-apply-twice guard and every outcome metric downstream.
    """
    outcome = await in_session(container, lambda s: s.submission.confirm_manual_submission(job_id))
    if not outcome.submitted:
        raise HTTPException(status.HTTP_409_CONFLICT, outcome.reason or "could not record")
    return asdict(outcome)


@router.post("/prepare-forms")
async def prepare_forms(
    container: Annotated[Container, Depends(get_container)],
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """Open one browser tab per selected job, each with the form already drafted.

    Tabs stay open until you close them -- nothing is submitted and nothing times out. `skipped` explains any
    job that was not opened (already applied, no tailored resume yet, over the tab limit).
    """
    job_ids = payload.get("job_ids")
    if not isinstance(job_ids, list) or not job_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expected a non-empty 'job_ids' list")

    try:
        batch = await in_session(
            container, lambda s: s.submission.prepare_forms([str(j) for j in job_ids])
        )
    except AnswersIncompleteError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    return {
        "counts": batch.counts,
        "browser_left_open": batch.browser_left_open,
        "prepared": [asdict(item) for item in batch.prepared],
        "skipped": [asdict(item) for item in batch.skipped],
    }
