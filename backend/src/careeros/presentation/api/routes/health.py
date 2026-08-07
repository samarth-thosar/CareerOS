"""GET /health -- a real database round-trip, not a hardcoded response.

Proves the composition root, the async engine, and the FastAPI wiring actually work end to end before any
feature endpoint exists.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.presentation.api.dependencies import get_session

router = APIRouter()


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
