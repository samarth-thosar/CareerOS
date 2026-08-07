"""CoverLetterService -- generates cover letters from a tailored resume.

Implemented in Phase 7 (Resume Manager).
"""
from __future__ import annotations

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.llm_provider import LLMProvider
from careeros.domain.repositories import ResumeRepository


class CoverLetterService:
    def __init__(
        self,
        resume_repository: ResumeRepository,
        llm_provider: LLMProvider,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._resume_repository = resume_repository
        self._llm_provider = llm_provider
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator

    async def generate_for_resume(self, resume_version_id: str, job_id: str) -> None:
        """Generate a cover letter for a rendered resume version and publish CoverLetterGenerated."""
        raise NotImplementedError("Cover letter generation is implemented in Phase 7")
