"""ResumeManagerService -- tailors resumes from the Overleaf master and renders PDFs.

Implemented in Phase 7 (Resume Manager). Emits ResumeGapFlag instead of fabricating content it can't
honestly support -- see docs/architecture/01-domain-model.md, ResumeGapFlag.
"""
from __future__ import annotations

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.llm_provider import LLMProvider
from careeros.application.ports.resume_source import ResumeSource
from careeros.domain.repositories import JobRepository, ResumeRepository


class ResumeManagerService:
    def __init__(
        self,
        resume_repository: ResumeRepository,
        job_repository: JobRepository,
        resume_source: ResumeSource,
        llm_provider: LLMProvider,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._resume_repository = resume_repository
        self._job_repository = job_repository
        self._resume_source = resume_source
        self._llm_provider = llm_provider
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator

    async def tailor_for_job(self, job_id: str, application_id: str) -> None:
        """Tailor the master resume for a job, render a PDF, and publish ResumeGenerated."""
        raise NotImplementedError("Resume tailoring is implemented in Phase 7")
