"""Tests for the anti-fabrication guarantees.

This is the most important test file in the resume subsystem. The promise to the user is that a generated
resume never claims anything they cannot back up, and these are the checks that make that true rather than
aspirational -- so each realistic way a model could smuggle in unsupported content gets its own case.
"""
from __future__ import annotations

import pytest

from careeros.domain.resume.achievement import (
    Achievement,
    AchievementBank,
    AchievementKind,
    UnknownAchievementError,
    UnknownBulletError,
)
from careeros.domain.resume.tailoring import (
    AchievementSelection,
    BulletSelection,
    FabricationError,
    TailoringPlan,
    validate_plan,
    validate_rephrasing,
)

CLAIMABLE_SKILLS = ["python", "react"]


def _bank() -> AchievementBank:
    return AchievementBank(
        achievements=[
            Achievement(
                id="role-a",
                kind=AchievementKind.EXPERIENCE,
                title="Software Engineer",
                bullets=[
                    "Built REST APIs handling 200 requests per second.",
                    "Added automated tests to an untested service.",
                ],
                technologies=["python", "fastapi"],
            ),
            Achievement(
                id="project-b",
                kind=AchievementKind.PROJECT,
                title="RAG Tool",
                bullets=["Built a retrieval pipeline over private documents."],
                technologies=["llm", "rag"],
            ),
        ]
    )


def _plan(**overrides) -> TailoringPlan:
    defaults = {
        "achievements": [AchievementSelection("role-a", [BulletSelection(0)])],
        "skills": ["python"],
        "summary": "Engineer.",
        "gaps": [],
    }
    return TailoringPlan(**{**defaults, **overrides})


class TestRephrasingGuard:
    def test_reword_without_new_figures_is_allowed(self) -> None:
        validate_rephrasing(
            "Built REST APIs handling 200 requests per second.",
            "Designed REST APIs serving 200 requests per second.",
        )

    def test_dropping_a_figure_is_allowed(self) -> None:
        # Shortening a bullet is legitimate tailoring.
        validate_rephrasing("Built REST APIs handling 200 requests per second.", "Built REST APIs.")

    @pytest.mark.parametrize(
        "invented",
        [
            "Built REST APIs handling 5000 requests per second.",
            "Built REST APIs, improving latency by 40%.",
            "Built REST APIs across 12 services.",
        ],
    )
    def test_inventing_a_metric_is_rejected(self, invented: str) -> None:
        # The most damaging kind of resume fabrication, and the cheapest to catch exactly.
        with pytest.raises(FabricationError, match="figures absent"):
            validate_rephrasing("Built REST APIs handling 200 requests per second.", invented)

    def test_comma_grouping_is_normalized_not_treated_as_new(self) -> None:
        validate_rephrasing("Processed 1200 events.", "Processed 1,200 events.")

    def test_reusing_an_existing_figure_differently_is_allowed(self) -> None:
        validate_rephrasing("Handled 200 requests per second.", "Sustained 200 req/s throughput.")


class TestPlanValidation:
    def test_a_supported_plan_passes(self) -> None:
        validate_plan(_plan(), _bank(), CLAIMABLE_SKILLS)

    def test_unknown_achievement_id_is_rejected(self) -> None:
        plan = _plan(achievements=[AchievementSelection("invented-role", [BulletSelection(0)])])

        with pytest.raises(UnknownAchievementError):
            validate_plan(plan, _bank(), CLAIMABLE_SKILLS)

    def test_out_of_range_bullet_index_is_rejected(self) -> None:
        plan = _plan(achievements=[AchievementSelection("project-b", [BulletSelection(7)])])

        with pytest.raises(UnknownBulletError):
            validate_plan(plan, _bank(), CLAIMABLE_SKILLS)

    def test_skill_the_candidate_never_claimed_is_rejected(self) -> None:
        plan = _plan(skills=["python", "kubernetes"])

        with pytest.raises(FabricationError, match="kubernetes"):
            validate_plan(plan, _bank(), CLAIMABLE_SKILLS)

    def test_technologies_from_the_bank_count_as_claimable(self) -> None:
        # "fastapi" is not in the profile's skills list but is evidenced by an achievement, so it is fair.
        validate_plan(_plan(skills=["fastapi"]), _bank(), CLAIMABLE_SKILLS)

    def test_skill_matching_ignores_case(self) -> None:
        validate_plan(_plan(skills=["Python", "REACT"]), _bank(), CLAIMABLE_SKILLS)

    def test_invented_figure_inside_a_plan_is_rejected(self) -> None:
        plan = _plan(
            achievements=[
                AchievementSelection("role-a", [BulletSelection(0, rephrased="Served 9000 requests/sec.")])
            ]
        )

        with pytest.raises(FabricationError, match="figures absent"):
            validate_plan(plan, _bank(), CLAIMABLE_SKILLS)

    def test_empty_selection_is_rejected(self) -> None:
        with pytest.raises(FabricationError, match="no achievements"):
            validate_plan(_plan(achievements=[]), _bank(), CLAIMABLE_SKILLS)

    def test_achievement_with_no_bullets_is_rejected(self) -> None:
        plan = _plan(achievements=[AchievementSelection("role-a", [])])

        with pytest.raises(FabricationError, match="no bullets"):
            validate_plan(plan, _bank(), CLAIMABLE_SKILLS)

    def test_duplicate_achievement_selection_is_rejected(self) -> None:
        plan = _plan(
            achievements=[
                AchievementSelection("role-a", [BulletSelection(0)]),
                AchievementSelection("role-a", [BulletSelection(1)]),
            ]
        )

        with pytest.raises(FabricationError, match="more than once"):
            validate_plan(plan, _bank(), CLAIMABLE_SKILLS)


class TestBankIntegrity:
    def test_duplicate_ids_are_rejected(self) -> None:
        achievement = Achievement(
            id="same", kind=AchievementKind.PROJECT, title="X", bullets=["Did a thing."]
        )

        with pytest.raises(ValueError, match="Duplicate achievement ids"):
            AchievementBank(achievements=[achievement, achievement])

    def test_achievement_needs_at_least_one_bullet(self) -> None:
        with pytest.raises(ValueError, match="at least one bullet"):
            Achievement(id="x", kind=AchievementKind.PROJECT, title="X", bullets=[])

    def test_strength_outside_one_to_five_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="strength"):
            Achievement(
                id="x", kind=AchievementKind.PROJECT, title="X", bullets=["Did it."], strength=9
            )

    def test_all_technologies_deduplicates_preserving_order(self) -> None:
        assert _bank().all_technologies() == ["python", "fastapi", "llm", "rag"]

    def test_bullet_selection_falls_back_to_the_original(self) -> None:
        assert BulletSelection(0).render("Original text.") == "Original text."
        assert BulletSelection(0, rephrased="New text.").render("Original text.") == "New text."


class TestReworkDetection:
    """Models often echo the original into `rephrased`; a diff must not call that a change."""

    def test_absent_rephrasing_is_not_a_rewording(self) -> None:
        assert BulletSelection(0).is_rewording("Built APIs.") is False

    def test_identical_rephrasing_is_not_a_rewording(self) -> None:
        assert BulletSelection(0, rephrased="Built APIs.").is_rewording("Built APIs.") is False

    def test_whitespace_only_difference_is_not_a_rewording(self) -> None:
        assert BulletSelection(0, rephrased="  Built APIs. ").is_rewording("Built APIs.") is False

    def test_genuine_change_is_a_rewording(self) -> None:
        assert BulletSelection(0, rephrased="Designed APIs.").is_rewording("Built APIs.") is True

    def test_stripping_bold_markers_is_not_a_rewording(self) -> None:
        # Regression: qwen3 echoed every bullet back with **emphasis** removed. That is a formatting loss, not
        # an edit, and treating it as one discarded the emphasis from the generated resume.
        selection = BulletSelection(0, rephrased="Built an AI-powered platform.")

        assert selection.is_rewording("Built an **AI-powered platform**.") is False

    def test_bold_is_preserved_when_the_model_strips_it(self) -> None:
        original = "Built an **AI-powered platform**."
        selection = BulletSelection(0, rephrased="Built an AI-powered platform.")

        assert selection.render(original) == original

    def test_a_real_edit_still_wins_over_the_original(self) -> None:
        original = "Building an **AI-powered platform**."
        selection = BulletSelection(0, rephrased="Built an AI-powered platform.")

        assert selection.is_rewording(original) is True
        assert selection.render(original) == "Built an AI-powered platform."

    def test_added_emphasis_alone_is_not_a_rewording(self) -> None:
        selection = BulletSelection(0, rephrased="Built an **AI-powered** platform.")

        assert selection.is_rewording("Built an AI-powered platform.") is False
