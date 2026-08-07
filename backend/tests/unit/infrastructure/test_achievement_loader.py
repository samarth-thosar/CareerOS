"""Tests for achievement bank loading and validation.

The committed-file test is the important one here: a YAML mistake in the real bank breaks tailoring entirely,
and the failure mode looks like the model underperforming rather than a config error. (It caught exactly that
-- plain scalars containing "word: **bold**" made YAML read a mapping whose value began with `*`, which it
rejects as an alias reference.)
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from careeros.domain.resume.achievement import AchievementKind
from careeros.infrastructure.resume.achievement_loader import (
    DEFAULT_ACHIEVEMENTS_PATH,
    AchievementBankError,
    load_achievement_bank,
)

VALID = {
    "achievements": [
        {
            "id": "role-a",
            "kind": "experience",
            "title": "Engineer",
            "organization": "Acme",
            "start_date": "2024-01",
            "end_date": "present",
            "strength": 5,
            "technologies": ["python"],
            "bullets": ["Built APIs.", "Wrote tests."],
        },
        {
            "id": "project-b",
            "kind": "project",
            "title": "Side Project",
            "bullets": ["Shipped a thing."],
        },
    ]
}


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "achievements.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class TestLoading:
    def test_loads_a_valid_bank(self, tmp_path: Path) -> None:
        bank = load_achievement_bank(_write(tmp_path, VALID))

        assert bank.ids == {"role-a", "project-b"}
        assert bank.get("role-a").kind is AchievementKind.EXPERIENCE
        assert bank.get("role-a").bullets == ["Built APIs.", "Wrote tests."]

    def test_optional_fields_default_sensibly(self, tmp_path: Path) -> None:
        bank = load_achievement_bank(_write(tmp_path, VALID))
        project = bank.get("project-b")

        assert project.organization is None
        assert project.technologies == []
        assert project.strength == 3

    def test_kinds_are_separable(self, tmp_path: Path) -> None:
        bank = load_achievement_bank(_write(tmp_path, VALID))

        assert [a.id for a in bank.of_kind(AchievementKind.EXPERIENCE)] == ["role-a"]
        assert [a.id for a in bank.of_kind(AchievementKind.PROJECT)] == ["project-b"]

    def test_blank_bullets_are_dropped(self, tmp_path: Path) -> None:
        data = {"achievements": [{**VALID["achievements"][1], "bullets": ["Real.", "  ", ""]}]}

        assert load_achievement_bank(_write(tmp_path, data)).get("project-b").bullets == ["Real."]


class TestValidation:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AchievementBankError, match="No achievement bank"):
            load_achievement_bank(tmp_path / "absent.yaml")

    def test_missing_achievements_key_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AchievementBankError, match="achievements"):
            load_achievement_bank(_write(tmp_path, {"stuff": []}))

    def test_empty_list_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AchievementBankError, match="non-empty"):
            load_achievement_bank(_write(tmp_path, {"achievements": []}))

    def test_unknown_kind_raises_and_names_the_valid_options(self, tmp_path: Path) -> None:
        data = {"achievements": [{**VALID["achievements"][1], "kind": "hobby"}]}

        with pytest.raises(AchievementBankError, match="experience"):
            load_achievement_bank(_write(tmp_path, data))

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        data = {"achievements": [{"id": "x", "kind": "project", "title": "X"}]}

        with pytest.raises(AchievementBankError, match="bullets"):
            load_achievement_bank(_write(tmp_path, data))

    def test_achievement_with_only_blank_bullets_raises(self, tmp_path: Path) -> None:
        data = {"achievements": [{**VALID["achievements"][1], "bullets": ["  "]}]}

        with pytest.raises(AchievementBankError, match="at least one bullet"):
            load_achievement_bank(_write(tmp_path, data))

    def test_duplicate_ids_raise(self, tmp_path: Path) -> None:
        entry = VALID["achievements"][1]
        with pytest.raises(AchievementBankError, match="Duplicate"):
            load_achievement_bank(_write(tmp_path, {"achievements": [entry, entry]}))

    def test_out_of_range_strength_raises(self, tmp_path: Path) -> None:
        data = {"achievements": [{**VALID["achievements"][1], "strength": 0}]}

        with pytest.raises(AchievementBankError, match="strength"):
            load_achievement_bank(_write(tmp_path, data))


class TestCommittedBank:
    """A fresh clone must be able to tailor, so the shipped bank has to parse and be usable."""

    def test_the_committed_bank_loads(self) -> None:
        bank = load_achievement_bank(DEFAULT_ACHIEVEMENTS_PATH)

        assert len(bank.achievements) >= 2
        assert bank.of_kind(AchievementKind.EXPERIENCE), "expected at least one work-experience entry"
        assert bank.of_kind(AchievementKind.PROJECT), "expected at least one project entry"

    def test_every_bullet_is_non_trivial(self) -> None:
        bank = load_achievement_bank(DEFAULT_ACHIEVEMENTS_PATH)

        for achievement in bank.achievements:
            for bullet in achievement.bullets:
                assert len(bullet) > 20, f"suspiciously short bullet on {achievement.id!r}: {bullet!r}"

    def test_bold_markers_are_balanced(self) -> None:
        # An odd count means a stray "**" that would render literally instead of as emphasis.
        bank = load_achievement_bank(DEFAULT_ACHIEVEMENTS_PATH)

        for achievement in bank.achievements:
            for bullet in achievement.bullets:
                assert bullet.count("**") % 2 == 0, f"unbalanced bold markers on {achievement.id!r}: {bullet!r}"
