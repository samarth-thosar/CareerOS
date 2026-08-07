"""APSchedulerAdapter -- the phase-1 SchedulerPort adapter, wrapping APScheduler's AsyncIOScheduler.

Uses the in-memory job store for now, since no recurring job is registered yet in this phase (see
careeros.infrastructure.bootstrap). Moving to a persistent SQLAlchemy job store -- so cycles survive
restarts without duplicate firing, per docs/architecture/04-scheduler-config-and-testing.md -- requires job
callables to be picklable module-level references rather than closures over live service instances; that
registry is introduced alongside the first real recurring job (job discovery, Phase 4).
"""
from __future__ import annotations

import logging

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from careeros.application.ports.scheduler_port import CoroFactory

logger = logging.getLogger(__name__)


class APSchedulerAdapter:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(executors={"default": AsyncIOExecutor()})

    def schedule_interval(self, job_id: str, coro_factory: CoroFactory, seconds: int) -> None:
        self._scheduler.add_job(
            self._run_safely,
            trigger=IntervalTrigger(seconds=seconds),
            args=[job_id, coro_factory],
            id=job_id,
            max_instances=1,
            replace_existing=True,
        )

    def schedule_cron(self, job_id: str, coro_factory: CoroFactory, cron_expression: str) -> None:
        self._scheduler.add_job(
            self._run_safely,
            trigger=CronTrigger.from_crontab(cron_expression),
            args=[job_id, coro_factory],
            id=job_id,
            max_instances=1,
            replace_existing=True,
        )

    def remove(self, job_id: str) -> None:
        self._scheduler.remove_job(job_id)

    async def start(self) -> None:
        self._scheduler.start()

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    @staticmethod
    async def _run_safely(job_id: str, coro_factory: CoroFactory) -> None:
        try:
            await coro_factory()
        except Exception:
            logger.exception("Scheduled job %s failed", job_id)
