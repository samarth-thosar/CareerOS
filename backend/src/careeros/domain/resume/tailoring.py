"""Tailoring selections and the checks that keep them honest.

A `TailoringPlan` is what the model is allowed to decide: which achievements to include, in what order, which
of their existing bullets to use, and optional rewording. It cannot introduce content -- every id and bullet
index is resolved against the achievement bank, and every claimed skill against the candidate's own list.

`validate_rephrasing` is the last line of defence. Rewording is where fabrication would realistically slip in,
and the most damaging form is an invented metric ("reduced latency by 40%" where the original said no such
thing). Numbers are cheap to verify exactly, so any figure in a reworded bullet that is absent from the
original is rejected outright.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from careeros.domain.resume.achievement import AchievementBank

# Matches integers, decimals, percentages and comma-grouped figures, ignoring surrounding words.
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


class FabricationError(ValueError):
    """Raised when a tailoring selection would put unsupported content on a resume."""


@dataclass(frozen=True, slots=True)
class BulletSelection:
    """One approved bullet, optionally reworded for this job."""

    source_index: int
    rephrased: str | None = None

    def render(self, original: str) -> str:
        return self.rephrased if self.rephrased else original

    def is_rewording(self, original: str) -> bool:
        """Whether this actually changes the text.

        Models frequently echo the original back in `rephrased`. The raw response is still recorded verbatim
        for auditability, but a diff that labels unchanged text "reworded" hides the changes that do matter.
        """
        if not self.rephrased:
            return False
        return self.rephrased.strip() != original.strip()


@dataclass(frozen=True, slots=True)
class AchievementSelection:
    achievement_id: str
    bullets: list[BulletSelection]


@dataclass(frozen=True, slots=True)
class TailoringPlan:
    """The model's decisions for one job, before validation."""

    achievements: list[AchievementSelection]
    skills: list[str] = field(default_factory=list)
    summary: str | None = None
    gaps: list[str] = field(default_factory=list)


def _numbers_in(text: str) -> set[str]:
    """Numeric tokens in `text`, normalized so "1,200" and "1200" compare equal."""
    return {match.group().replace(",", "") for match in _NUMBER.finditer(text)}


def validate_rephrasing(original: str, rephrased: str) -> None:
    """Reject a reworded bullet that introduces a figure the original did not contain.

    Deliberately one-directional: dropping a number is fine (shortening a bullet), inventing one is not.
    """
    invented = _numbers_in(rephrased) - _numbers_in(original)
    if invented:
        raise FabricationError(
            f"Reworded bullet introduces figures absent from the original {sorted(invented)}: {rephrased!r}"
        )


def validate_plan(plan: TailoringPlan, bank: AchievementBank, claimable_skills: list[str]) -> None:
    """Check every part of a plan against what the candidate can actually claim.

    Raises on the first problem found. Callers treat this as fatal for the job being tailored rather than
    silently dropping the offending item, because a plan that tried to fabricate once is not trustworthy for
    the rest of its selections either.
    """
    if not plan.achievements:
        raise FabricationError("Tailoring plan selected no achievements")

    seen_ids: set[str] = set()
    for selection in plan.achievements:
        if selection.achievement_id in seen_ids:
            raise FabricationError(f"Achievement {selection.achievement_id!r} selected more than once")
        seen_ids.add(selection.achievement_id)

        achievement = bank.get(selection.achievement_id)  # raises UnknownAchievementError if invented
        if not selection.bullets:
            raise FabricationError(f"Achievement {selection.achievement_id!r} selected with no bullets")

        for bullet in selection.bullets:
            original = achievement.bullet(bullet.source_index)  # raises if the index is invented
            if bullet.rephrased:
                validate_rephrasing(original, bullet.rephrased)

    claimable = {skill.lower() for skill in claimable_skills} | {
        technology.lower() for technology in bank.all_technologies()
    }
    unsupported = sorted({skill for skill in plan.skills if skill.lower() not in claimable})
    if unsupported:
        raise FabricationError(f"Tailoring plan claims skills the candidate has not listed: {unsupported}")
