"""ApplicationTrackerService -- owns Application lifecycle transitions across the event-driven pipeline.

The Application aggregate's own invariants (never-apply-twice, the state machine) are implemented and
tested now (see careeros.domain.application.application); this service's event-reaction methods are
implemented in Phase 9 (Application Tracker).
"""
from __future__ import annotations

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.domain.repositories import ApplicationRepository


class ApplicationTrackerService:
    def __init__(
        self,
        application_repository: ApplicationRepository,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._application_repository = application_repository
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator

    async def handle_job_discovered(self, job_id: str, company_id: str) -> None:
        """Create an Application(status=Found) for a newly discovered job."""
        raise NotImplementedError("Application tracking is implemented in Phase 9")

    async def handle_job_scored(self, job_id: str, score_value: int) -> None:
        """Maybe transition Found -> Interested based on the auto-interested threshold."""
        raise NotImplementedError("Application tracking is implemented in Phase 9")
