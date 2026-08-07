"""DiscoveryService -- orchestrates job discovery cycles across enabled JobSourceProviders.

Implemented in Phase 4 (Job Discovery). Only constructor wiring and the public interface are real in this
phase -- see docs/architecture/03-event-catalog-and-pipeline.md, pipeline step 1.
"""
from __future__ import annotations

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.job_source_provider import JobSourceProvider
from careeros.domain.repositories import CompanyRepository, JobRepository


class DiscoveryService:
    def __init__(
        self,
        providers: list[JobSourceProvider],
        job_repository: JobRepository,
        company_repository: CompanyRepository,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._providers = providers
        self._job_repository = job_repository
        self._company_repository = company_repository
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator

    async def run_cycle(self, provider_name: str) -> None:
        """Search one provider, de-duplicate results, persist new Jobs, and publish JobDiscovered."""
        raise NotImplementedError("Job discovery is implemented in Phase 4")
