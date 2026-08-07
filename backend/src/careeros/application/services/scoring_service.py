"""ScoringService -- produces LLM-based Job scores.

Implemented in Phase 6 (Job Scoring). See docs/architecture/03-event-catalog-and-pipeline.md, pipeline
step 3.
"""
from __future__ import annotations

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.llm_provider import LLMProvider
from careeros.domain.repositories import CandidateProfileRepository, JobRepository, ScoreRepository


class ScoringService:
    def __init__(
        self,
        job_repository: JobRepository,
        score_repository: ScoreRepository,
        candidate_profile_repository: CandidateProfileRepository,
        llm_provider: LLMProvider,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._job_repository = job_repository
        self._score_repository = score_repository
        self._candidate_profile_repository = candidate_profile_repository
        self._llm_provider = llm_provider
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator

    async def score_job(self, job_id: str) -> None:
        """Score a single job against the candidate profile and publish JobScored."""
        raise NotImplementedError("Job scoring is implemented in Phase 6")
