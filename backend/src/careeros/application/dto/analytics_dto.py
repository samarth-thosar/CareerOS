"""Analytics DTOs.

Scoped deliberately to what the database can currently answer. Interview rate, response rate and offer counts
are all in the product vision, but no application has yet reached those states, so shipping those tiles now
would mean shipping zeros that look like failure rather than like "not yet". They arrive with the phases that
produce their data.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Count:
    """One label/value pair, for the breakdown lists."""

    label: str
    value: int


@dataclass(slots=True)
class ScoreBucket:
    """A 10-wide score band, so the distribution can be read as a histogram."""

    floor: int
    count: int


@dataclass(slots=True)
class Overview:
    jobs_total: int
    jobs_scored: int
    jobs_unscored: int
    companies: int
    applications_by_status: dict[str, int]
    resume_versions: int
    pending_gaps: int
    shortlist_size: int
    shortlist_threshold: int
    top_score: int | None
    median_score: int | None


@dataclass(slots=True)
class Breakdowns:
    score_distribution: list[ScoreBucket] = field(default_factory=list)
    top_technologies: list[Count] = field(default_factory=list)
    top_companies: list[Count] = field(default_factory=list)
    remote_split: list[Count] = field(default_factory=list)
    discovery_by_day: list[Count] = field(default_factory=list)
