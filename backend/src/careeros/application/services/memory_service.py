"""MemoryService -- recomputes outcome-correlation read-models and writes suggested scoring-weight changes.

Suggestions are always written to a review queue, never applied to live configuration automatically -- see
docs/architecture/03-event-catalog-and-pipeline.md, "Memory feedback -- approval gate". Implemented in
Phase 12.
"""
from __future__ import annotations

from careeros.domain.repositories import ApplicationRepository, ScoreRepository


class MemoryService:
    def __init__(
        self,
        application_repository: ApplicationRepository,
        score_repository: ScoreRepository,
    ) -> None:
        self._application_repository = application_repository
        self._score_repository = score_repository

    async def recompute_insights(self) -> None:
        """Recompute response-rate/technology/resume-version correlations from repository data."""
        raise NotImplementedError("Memory is implemented in Phase 12")
