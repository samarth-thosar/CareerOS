"""Application tracking endpoints -- the durable record of every job CareerOS has acted on."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.infrastructure.persistence.read_models import ApplicationReadModel
from careeros.presentation.api.dependencies import get_session

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
