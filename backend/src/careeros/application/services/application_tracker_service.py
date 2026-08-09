"""ApplicationTrackerService -- owns the Application lifecycle in reaction to pipeline events.

Every discovered job gets an Application immediately, at status Found. That is deliberate: the Application is
the durable record of "we have seen this and here is everything that happened to it", so nothing can slip
through untracked, and the never-apply-twice invariant has a row to attach to from the very first sighting.

Handlers here are idempotent. Because each event handler runs in its own transaction (see
infrastructure/bootstrap.py), a retried or duplicated event must not create a second Application -- the unique
constraint on Application.job_id would reject it anyway, but failing loudly on a replay would be wrong.
"""
from __future__ import annotations

import logging

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.domain.application.application import Application, ApplicationStatus
from careeros.domain.events import ApplicationStatusChanged
from careeros.domain.repositories import ApplicationRepository

logger = logging.getLogger(__name__)


class ApplicationTrackerService:
    def __init__(
        self,
        application_repository: ApplicationRepository,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
        auto_interested_threshold: int,
    ) -> None:
        self._application_repository = application_repository
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator
        self._auto_interested_threshold = auto_interested_threshold

    async def track_discovered_job(self, job_id: str) -> Application:
        """Open (or return) the Application record for a job. Safe to call more than once per job."""
        existing = await self._application_repository.get_by_job_id(job_id)
        if existing is not None:
            logger.debug("Application already tracked for job %s", job_id)
            return existing

        application = Application.open(id=self._id_generator.new_id(), job_id=job_id, at=self._clock.now())
        await self._application_repository.add(application)
        logger.info("Tracking application %s for job %s", application.id, job_id)
        return application

    async def attach_resume(self, job_id: str, resume_version_id: str) -> None:
        """Advance to ResumeGenerated once a tailored resume exists for the job.

        Without this the lifecycle stalls: `Application.apply()` only permits a submission from
        ResumeGenerated, so a job could be tailored and still be unsubmittable. Idempotent, and tolerant of an
        application that has already moved further -- re-tailoring an applied job must not drag it backwards.
        """
        application = await self._application_repository.get_by_job_id(job_id)
        if application is None:
            logger.warning("Resume generated for untracked job %s", job_id)
            return

        application.current_resume_version_id = resume_version_id
        if application.status not in (ApplicationStatus.FOUND, ApplicationStatus.INTERESTED, ApplicationStatus.SAVED):
            # Already at ResumeGenerated or beyond; record the newer resume and leave the status alone.
            await self._application_repository.save(application)
            return

        now = self._clock.now()
        previous = application.status
        # Found -> ResumeGenerated is not a legal single step, so pass through Interested first.
        if previous is ApplicationStatus.FOUND:
            application.transition_to(ApplicationStatus.INTERESTED, at=now, reason="resume tailored")
        application.transition_to(ApplicationStatus.RESUME_GENERATED, at=now, reason="resume tailored")
        await self._application_repository.save(application)
        await self._event_bus.publish(
            ApplicationStatusChanged(
                application_id=application.id,
                job_id=job_id,
                from_status=previous.value,
                to_status=ApplicationStatus.RESUME_GENERATED.value,
                reason="resume tailored",
            )
        )

    async def record_cover_letter(self, job_id: str, cover_letter_id: str) -> None:
        """Attach a cover letter. No status change -- a letter alone does not advance the lifecycle."""
        application = await self._application_repository.get_by_job_id(job_id)
        if application is None:
            return
        application.current_cover_letter_id = cover_letter_id
        await self._application_repository.save(application)

    async def apply_score(self, job_id: str, score_value: int) -> None:
        """Promote Found -> Interested when a score clears the configured threshold.

        Below the threshold the Application deliberately stays at Found rather than being auto-rejected --
        a low score is CareerOS's opinion, not a decision, and the row remains visible on the dashboard.
        """
        application = await self._application_repository.get_by_job_id(job_id)
        if application is None:
            logger.warning("Scored job %s has no tracked application", job_id)
            return
        if application.status is not ApplicationStatus.FOUND:
            return
        if score_value < self._auto_interested_threshold:
            return

        now = self._clock.now()
        application.transition_to(
            ApplicationStatus.INTERESTED, at=now, reason=f"score {score_value} cleared threshold"
        )
        await self._application_repository.save(application)
        await self._event_bus.publish(
            ApplicationStatusChanged(
                application_id=application.id,
                job_id=job_id,
                from_status=ApplicationStatus.FOUND.value,
                to_status=ApplicationStatus.INTERESTED.value,
                reason=f"score {score_value} cleared threshold",
            )
        )
