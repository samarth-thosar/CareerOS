"""Dashboard analytics endpoints."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.infrastructure.bootstrap import Container
from careeros.infrastructure.persistence.analytics_read_model import AnalyticsReadModel
from careeros.presentation.api.dependencies import get_container, get_session

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    container: Annotated[Container, Depends(get_container)],
) -> dict[str, Any]:
    """Headline counts for the dashboard, including how much of the scoring backlog is left."""
    threshold = container.settings.tracker.auto_interested_threshold
    return asdict(await AnalyticsReadModel(session).overview(shortlist_threshold=threshold))


@router.get("/breakdowns")
async def breakdowns(
    session: Annotated[AsyncSession, Depends(get_session)],
    top_n: Annotated[int, Query(ge=3, le=20)] = 8,
) -> dict[str, Any]:
    """Distributions behind the headline numbers: scores, technologies, companies, locations, discovery rate."""
    return asdict(await AnalyticsReadModel(session).breakdowns(top_n=top_n))
