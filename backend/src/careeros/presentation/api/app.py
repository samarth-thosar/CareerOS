"""FastAPI application factory.

Routers stay thin: parse request -> call an application service -> map to a response DTO. The composition
root's Container is built once at startup and stored on `app.state`; request handlers resolve
already-built services from there rather than constructing anything themselves. See
docs/architecture/00-overview.md.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from careeros.infrastructure.bootstrap import build_container
from careeros.infrastructure.logging import configure_logging
from careeros.presentation.api.routes.health import router as health_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = build_container()
    configure_logging(container.settings.log_level)
    app.state.container = container
    await container.scheduler.start()
    try:
        yield
    finally:
        await container.scheduler.shutdown()
        await container.engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="CareerOS", version="0.1.0", lifespan=_lifespan)
    app.include_router(health_router)
    return app
