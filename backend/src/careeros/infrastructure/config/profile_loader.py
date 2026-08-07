"""Loads config/profile.yaml into a CandidateProfile aggregate.

Kept separate from `settings.py` on purpose: settings are deployment tunables read on every boot, whereas the
profile is *seed data* for a database aggregate that the app then owns and evolves. Conflating them would
make it ambiguous whether a Memory-learned adjustment or the YAML wins.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from careeros.domain.candidate.candidate_profile import (
    CandidatePreferences,
    CandidateProfile,
    RoleInterest,
)

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[4] / "config" / "profile.yaml"

PROFILE_ID = "candidate"
"""Fixed id: CandidateProfile is a single-row aggregate, so reloading updates rather than duplicating."""


class ProfileConfigError(ValueError):
    """Raised when profile.yaml is missing or structurally invalid."""


def load_profile(path: Path | None = None) -> CandidateProfile:
    """Read and validate profile.yaml into a CandidateProfile.

    Validation is strict and fails loudly: a silently half-loaded profile would degrade every score the system
    produces afterwards, in a way that looks like the model performing badly rather than a config mistake.
    """
    profile_path = path or DEFAULT_PROFILE_PATH
    if not profile_path.exists():
        raise ProfileConfigError(f"No profile file at {profile_path}")

    with profile_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ProfileConfigError(f"{profile_path} must contain a YAML mapping")

    return CandidateProfile(
        id=PROFILE_ID,
        headline=_optional_str(raw, "headline"),
        summary=_optional_str(raw, "summary"),
        years_experience=_optional_float(raw, "years_experience"),
        skills=_string_list(raw, "skills"),
        role_interests=_role_interests(raw.get("role_interests") or []),
        preferences=_preferences(raw.get("preferences") or {}),
        do_not_apply_companies=_string_list(raw, "do_not_apply_companies"),
    )


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    return str(value).strip() or None


def _optional_float(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ProfileConfigError(f"{key!r} must be a number, got {value!r}") from error


def _string_list(raw: dict[str, Any], key: str) -> list[str]:
    value = raw.get(key) or []
    if not isinstance(value, list):
        raise ProfileConfigError(f"{key!r} must be a list, got {type(value).__name__}")
    return [str(item).strip() for item in value if str(item).strip()]


def _role_interests(raw_roles: Any) -> list[RoleInterest]:
    if not isinstance(raw_roles, list):
        raise ProfileConfigError("'role_interests' must be a list")

    roles: list[RoleInterest] = []
    for entry in raw_roles:
        if not isinstance(entry, dict) or "title" not in entry or "priority" not in entry:
            raise ProfileConfigError(f"Each role_interests entry needs 'title' and 'priority'; got {entry!r}")
        try:
            roles.append(RoleInterest(title=str(entry["title"]).strip(), priority=int(entry["priority"])))
        except ValueError as error:
            raise ProfileConfigError(f"Invalid role_interests entry {entry!r}: {error}") from error
    return roles


def _preferences(raw_preferences: Any) -> CandidatePreferences | None:
    if not raw_preferences:
        return None
    if not isinstance(raw_preferences, dict):
        raise ProfileConfigError("'preferences' must be a mapping")

    remote = str(raw_preferences.get("remote_preference") or "any").strip().lower()
    allowed = {"remote", "hybrid", "onsite", "any"}
    if remote not in allowed:
        raise ProfileConfigError(f"'remote_preference' must be one of {sorted(allowed)}, got {remote!r}")

    return CandidatePreferences(
        remote_preference=remote,
        salary_floor=_optional_float(raw_preferences, "salary_floor"),
        target_skill_areas=_string_list(raw_preferences, "target_skill_areas"),
        preferred_locations=_string_list(raw_preferences, "preferred_locations"),
    )
