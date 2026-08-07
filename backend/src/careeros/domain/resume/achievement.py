"""The achievement bank -- the only content a tailored resume may draw from.

This is what makes "never invent experience" structural rather than a prompt instruction. Tailoring does not
write prose; it *selects* achievements by id from this bank and may reword existing bullets. Anything a job
needs that the bank cannot support becomes a ResumeGapFlag for the candidate to approve, never text the model
made up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AchievementKind(StrEnum):
    EXPERIENCE = "experience"
    PROJECT = "project"


class UnknownAchievementError(LookupError):
    """Raised when a selection references an achievement id that is not in the bank."""


class UnknownBulletError(LookupError):
    """Raised when a selection references a bullet index an achievement does not have."""


@dataclass(frozen=True, slots=True)
class Achievement:
    """One role or project the candidate can genuinely claim.

    `bullets` are the approved statements. Tailoring may reorder them, choose a subset, or reword them, but
    may never add one -- so every line on a generated resume traces back to a bullet here.
    """

    id: str
    kind: AchievementKind
    title: str
    bullets: list[str]
    organization: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    technologies: list[str] = field(default_factory=list)
    url: str | None = None
    # 1-5, the candidate's own view of how strong this is. Used to break ties when a job fits several equally.
    strength: int = 3

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Achievement id cannot be blank")
        if not self.bullets:
            raise ValueError(f"Achievement {self.id!r} must have at least one bullet")
        if not 1 <= self.strength <= 5:
            raise ValueError(f"Achievement {self.id!r} strength must be 1-5, got {self.strength}")

    def bullet(self, index: int) -> str:
        if not 0 <= index < len(self.bullets):
            raise UnknownBulletError(
                f"Achievement {self.id!r} has {len(self.bullets)} bullets; index {index} is out of range"
            )
        return self.bullets[index]


@dataclass(frozen=True, slots=True)
class AchievementBank:
    """The candidate's full set of claimable achievements, indexed by id."""

    achievements: list[Achievement]

    def __post_init__(self) -> None:
        ids = [achievement.id for achievement in self.achievements]
        duplicates = {id_ for id_ in ids if ids.count(id_) > 1}
        if duplicates:
            raise ValueError(f"Duplicate achievement ids in bank: {sorted(duplicates)}")

    def get(self, achievement_id: str) -> Achievement:
        for achievement in self.achievements:
            if achievement.id == achievement_id:
                return achievement
        raise UnknownAchievementError(f"No achievement with id {achievement_id!r} in the bank")

    def of_kind(self, kind: AchievementKind) -> list[Achievement]:
        return [achievement for achievement in self.achievements if achievement.kind is kind]

    @property
    def ids(self) -> set[str]:
        return {achievement.id for achievement in self.achievements}

    def all_technologies(self) -> list[str]:
        """Every technology appearing anywhere in the bank, deduplicated, first-seen order preserved."""
        seen: list[str] = []
        for achievement in self.achievements:
            for technology in achievement.technologies:
                if technology not in seen:
                    seen.append(technology)
        return seen
