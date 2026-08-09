"""Scoring and candidate-profile endpoints."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from careeros.infrastructure.bootstrap import Container, in_session
from careeros.presentation.api.dependencies import get_container

router = APIRouter(tags=["scoring"])


@router.post("/scoring/run")
async def run_scoring(
    container: Annotated[Container, Depends(get_container)],
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
) -> dict[str, Any]:
    """Score a slice of the backlog now instead of waiting for the scheduler.

    Each job is roughly a minute of local inference, so this is deliberately bounded and resumable: call it
    repeatedly (or let the scheduler do it) until `remaining` reaches zero.
    """
    batch_size = limit or container.settings.scoring.batch_size
    try:
        result = await in_session(container, lambda services: services.scoring.score_pending(batch_size))
    except Exception as error:
        # Most likely cause is a missing profile or an unreachable Ollama; both are actionable by the caller.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    return asdict(result)
