"""The Score aggregate -- immutable and append-only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    resume_match: float
    skill_area_fit: float
    career_progression_fit: float
    remote_fit: float
    salary_fit: float
    company_quality: float
    narrative: str


class InvalidScoreError(ValueError):
    """Raised when a score value falls outside the valid 0-100 range."""


@dataclass(frozen=True, slots=True)
class Score:
    """A single scoring result for a job, at a point in time.

    Re-scoring never mutates a `Score` -- a new one is inserted and the "current" score is the latest by
    `created_at`. This lets Memory correlate scoring-strategy versions with outcomes over time.
    """

    id: str
    job_id: str
    value: int
    explanation: ScoreBreakdown
    scoring_strategy_version: str
    model_used: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise InvalidScoreError(f"Score value must be within 0-100, got {self.value}")
