"""Loads data/master/achievements.yaml into an AchievementBank.

Validation is strict and fails loudly. A silently half-loaded bank would quietly narrow what tailoring can
draw from, producing thin resumes and spurious gap flags that look like the model underperforming rather than
a YAML mistake.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from careeros.domain.resume.achievement import Achievement, AchievementBank, AchievementKind

DEFAULT_ACHIEVEMENTS_PATH = Path(__file__).resolve().parents[4] / "data" / "master" / "achievements.yaml"


class AchievementBankError(ValueError):
    """Raised when the achievement bank file is missing or structurally invalid."""


def load_achievement_bank(path: Path | None = None) -> AchievementBank:
    bank_path = path or DEFAULT_ACHIEVEMENTS_PATH
    if not bank_path.exists():
        raise AchievementBankError(f"No achievement bank at {bank_path}")

    with bank_path.open("r", encoding="utf-8") as handle:
        raw: Any = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict) or "achievements" not in raw:
        raise AchievementBankError(f"{bank_path} must be a mapping with an 'achievements' key")

    entries = raw["achievements"]
    if not isinstance(entries, list) or not entries:
        raise AchievementBankError("'achievements' must be a non-empty list")

    try:
        return AchievementBank(achievements=[_achievement(entry) for entry in entries])
    except (ValueError, TypeError) as error:
        raise AchievementBankError(str(error)) from error


def _achievement(entry: Any) -> Achievement:
    if not isinstance(entry, dict):
        raise AchievementBankError(f"Each achievement must be a mapping; got {entry!r}")

    for required in ("id", "kind", "title", "bullets"):
        if required not in entry:
            raise AchievementBankError(f"Achievement {entry.get('id', '<no id>')!r} is missing {required!r}")

    try:
        kind = AchievementKind(str(entry["kind"]).strip().lower())
    except ValueError as error:
        valid = [kind.value for kind in AchievementKind]
        raise AchievementBankError(
            f"Achievement {entry['id']!r} has kind {entry['kind']!r}; must be one of {valid}"
        ) from error

    bullets = entry["bullets"]
    if not isinstance(bullets, list):
        raise AchievementBankError(f"Achievement {entry['id']!r} bullets must be a list")
    cleaned_bullets = [str(bullet).strip() for bullet in bullets if str(bullet).strip()]

    technologies = entry.get("technologies") or []
    if not isinstance(technologies, list):
        raise AchievementBankError(f"Achievement {entry['id']!r} technologies must be a list")

    return Achievement(
        id=str(entry["id"]).strip(),
        kind=kind,
        title=str(entry["title"]).strip(),
        bullets=cleaned_bullets,
        organization=_optional(entry.get("organization")),
        start_date=_optional(entry.get("start_date")),
        end_date=_optional(entry.get("end_date")),
        technologies=[str(technology).strip() for technology in technologies if str(technology).strip()],
        url=_optional(entry.get("url")),
        strength=int(entry.get("strength", 3)),
    )


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None
