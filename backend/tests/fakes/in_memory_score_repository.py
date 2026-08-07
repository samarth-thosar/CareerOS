"""InMemoryScoreRepository -- test fake for ScoreRepository, preserving append-only semantics."""
from __future__ import annotations

from careeros.domain.scoring.score import Score


class InMemoryScoreRepository:
    def __init__(self) -> None:
        self.scores: list[Score] = []

    async def get_latest_for_job(self, job_id: str) -> Score | None:
        matching = [score for score in self.scores if score.job_id == job_id]
        return max(matching, key=lambda score: score.created_at) if matching else None

    async def add(self, score: Score) -> None:
        self.scores.append(score)
