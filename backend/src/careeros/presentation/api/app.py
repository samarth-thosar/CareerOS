"""FastAPI application factory.

Routers stay thin: parse request -> call an application service -> map to a response DTO. The composition
root's Container is built once at startup and stored on `app.state`; request handlers resolve
already-built services from there rather than constructing anything themselves. See
docs/architecture/00-overview.md.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from careeros.infrastructure.bootstrap import (
    build_container,
    in_session,
    register_event_handlers,
    register_scheduled_jobs,
    search_criteria_from,
)
from careeros.infrastructure.logging import configure_logging
from careeros.presentation.api.routes.applications import router as applications_router
from careeros.presentation.api.routes.health import router as health_router
from careeros.presentation.api.routes.jobs import router as jobs_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = build_container()
    configure_logging(container.settings.log_level)
    register_event_handlers(container)
    register_scheduled_jobs(container)
    app.state.container = container
    await container.scheduler.start()

    if container.settings.discovery.run_on_startup:
        await _run_startup_discovery(container)

    try:
        yield
    finally:
        await container.scheduler.shutdown()
        await container.engine.dispose()


async def _run_startup_discovery(container) -> None:
    """Optional immediate cycle on boot, for when waiting out the scheduler interval isn't wanted.

    Failures are logged rather than raised: a job source being unreachable must not stop the API from
    serving what is already in the database.
    """
    criteria = search_criteria_from(container.settings)
    for provider in container.job_source_providers:
        try:
            await in_session(container, lambda s, n=provider.name: s.discovery.run_cycle(n, criteria))
        except Exception:
            logger.exception("Startup discovery cycle failed for %s", provider.name)


def create_app() -> FastAPI:
    app = FastAPI(title="CareerOS", version="0.1.0", lifespan=_lifespan)
    # The Next.js dashboard runs on a different port in development, so it is a cross-origin caller.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(applications_router)
    return app
