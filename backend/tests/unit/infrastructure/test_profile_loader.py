"""Tests for profile.yaml loading and validation.

Validation failures must be loud: a half-loaded profile degrades every score afterwards in a way that looks
like the model performing badly rather than a config mistake, so these assert that bad input raises.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from careeros.infrastructure.config.profile_loader import (
    DEFAULT_PROFILE_PATH,
    ProfileConfigError,
    load_profile,
)

VALID = {
    "headline": "Software Engineer",
    "summary": "Builds backend and AI systems.",
    "years_experience": 2,
    "role_interests": [
        {"title": "AI Engineer", "priority": 5},
        {"title": "Backend Engineer", "priority": 4},
    ],
    "skills": ["python", "react"],
    "preferences": {
        "remote_preference": "remote",
        "salary_floor": 1_200_000,
        "target_skill_areas": ["ai", "backend"],
        "preferred_locations": ["Remote"],
    },
    "do_not_apply_companies": ["Bad Corp"],
}


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class TestLoading:
    def test_loads_a_valid_profile(self, tmp_path: Path) -> None:
        profile = load_profile(_write(tmp_path, VALID))

        assert profile.headline == "Software Engineer"
        assert profile.years_experience == 2
        assert profile.skills == ["python", "react"]
        assert profile.do_not_apply_companies == ["Bad Corp"]
        assert profile.preferences is not None
        assert profile.preferences.remote_preference == "remote"
        assert profile.preferences.salary_floor == 1_200_000

    def test_role_interests_are_parsed_and_rankable(self, tmp_path: Path) -> None:
        profile = load_profile(_write(tmp_path, VALID))

        assert [role.title for role in profile.top_roles(minimum_priority=5)] == ["AI Engineer"]
        assert len(profile.top_roles(minimum_priority=4)) == 2

    def test_profile_id_is_stable_so_reloading_updates_one_row(self, tmp_path: Path) -> None:
        first = load_profile(_write(tmp_path, VALID))
        second = load_profile(_write(tmp_path, {**VALID, "headline": "Changed"}))

        assert first.id == second.id

    def test_missing_optional_sections_are_tolerated(self, tmp_path: Path) -> None:
        profile = load_profile(_write(tmp_path, {"headline": "Dev"}))

        assert profile.skills == []
        assert profile.role_interests == []
        assert profile.preferences is None

    def test_blank_strings_become_none(self, tmp_path: Path) -> None:
        profile = load_profile(_write(tmp_path, {"headline": "   "}))

        assert profile.headline is None


class TestValidation:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ProfileConfigError, match="No profile file"):
            load_profile(tmp_path / "absent.yaml")

    def test_priority_outside_one_to_five_raises(self, tmp_path: Path) -> None:
        data = {**VALID, "role_interests": [{"title": "X", "priority": 9}]}

        with pytest.raises(ProfileConfigError, match="priority"):
            load_profile(_write(tmp_path, data))

    def test_role_entry_without_priority_raises(self, tmp_path: Path) -> None:
        data = {**VALID, "role_interests": [{"title": "X"}]}

        with pytest.raises(ProfileConfigError, match="priority"):
            load_profile(_write(tmp_path, data))

    def test_unknown_remote_preference_raises(self, tmp_path: Path) -> None:
        data = {**VALID, "preferences": {"remote_preference": "wherever"}}

        with pytest.raises(ProfileConfigError, match="remote_preference"):
            load_profile(_write(tmp_path, data))

    def test_non_numeric_years_experience_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ProfileConfigError, match="years_experience"):
            load_profile(_write(tmp_path, {**VALID, "years_experience": "a couple"}))

    def test_skills_as_a_string_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ProfileConfigError, match="skills"):
            load_profile(_write(tmp_path, {**VALID, "skills": "python"}))


def test_the_committed_profile_file_is_valid() -> None:
    """The default config/profile.yaml must always load, or a fresh clone cannot score anything."""
    profile = load_profile(DEFAULT_PROFILE_PATH)

    assert profile.role_interests, "the shipped profile should list target roles"
    assert profile.skills, "the shipped profile should list skills"
