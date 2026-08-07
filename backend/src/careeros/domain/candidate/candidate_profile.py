"""CandidateProfile -- the single-row 'who am I' business state Memory feeds back into.

Deliberately distinct from backend/config/*.yaml: config holds deployment-time tunables (scoring weights,
enabled providers, LLM choice); CandidateProfile holds business state that the app's own event-driven logic
evolves over time and must audit. The initial content is seeded from config/profile.yaml, but from then on it
is the database's copy that scoring reads, so learned adjustments have somewhere durable to live.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RoleInterest:
    """A target role and how much the candidate wants it, on a 1-5 scale.

    Scoring uses `priority` to judge role fit, which is why the candidate's own ranking is data rather than
    something the LLM is left to guess.
    """

    title: str
    priority: int

    def __post_init__(self) -> None:
        if not 1 <= self.priority <= 5:
            raise ValueError(f"RoleInterest priority must be 1-5, got {self.priority}")


@dataclass(slots=True)
class CandidatePreferences:
    remote_preference: str
    salary_floor: float | None
    target_skill_areas: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CandidateProfile:
    id: str
    headline: str | None = None
    summary: str | None = None
    years_experience: float | None = None
    master_resume_ref: str | None = None
    skills: list[str] = field(default_factory=list)
    role_interests: list[RoleInterest] = field(default_factory=list)
    preferences: CandidatePreferences | None = None
    do_not_apply_companies: list[str] = field(default_factory=list)
    auto_apply_enabled: bool = False
    auto_tailor_resume_enabled: bool = True

    def top_roles(self, minimum_priority: int = 4) -> list[RoleInterest]:
        """Role interests the candidate rated at least `minimum_priority`, highest first."""
        return sorted(
            (role for role in self.role_interests if role.priority >= minimum_priority),
            key=lambda role: role.priority,
            reverse=True,
        )
