"""FastAPI dependency-injection helpers.

Used only for request-scoped plumbing (resolving the container built by the composition root, opening a DB
session) -- never as a substitute for the constructor injection services use internally. See
docs/architecture/00-overview.md.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from careeros.infrastructure.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    container: Container = request.app.state.container
    async with container.session_factory() as session:
        yield session
