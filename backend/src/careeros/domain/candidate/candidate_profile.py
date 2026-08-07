"""CandidateProfile -- the single-row 'who am I' business state Memory feeds back into.

Deliberately distinct from backend/config/*.yaml: config holds deployment-time tunables (scoring weights,
enabled providers, LLM choice); CandidateProfile holds business state that the app's own event-driven logic
evolves over time and must audit.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CandidatePreferences:
    remote_preference: str
    salary_floor: float | None
    target_skill_areas: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CandidateProfile:
    id: str
    master_resume_ref: str | None = None
    skills: list[str] = field(default_factory=list)
    preferences: CandidatePreferences | None = None
    do_not_apply_companies: list[str] = field(default_factory=list)
    auto_apply_enabled: bool = False
    auto_tailor_resume_enabled: bool = True
