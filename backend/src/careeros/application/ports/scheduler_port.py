"""SchedulerPort -- the seam between an in-process AsyncIO scheduler (phase 1) and Celery Beat later.

Application services are invoked only through this port, never through direct scheduler-library calls in
service code, so a later Celery migration only touches the composition root. See
docs/architecture/04-scheduler-config-and-testing.md.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

CoroFactory = Callable[[], Awaitable[None]]


class SchedulerPort(Protocol):
    def schedule_interval(self, job_id: str, coro_factory: CoroFactory, seconds: int) -> None: ...
    def schedule_cron(self, job_id: str, coro_factory: CoroFactory, cron_expression: str) -> None: ...
    def remove(self, job_id: str) -> None: ...
    async def start(self) -> None: ...
    async def shutdown(self) -> None: ...
