"""Tests for deterministic .tex assembly.

Two properties are being protected: the master template's structure survives untouched (so the model can never
break the document), and bank content is escaped rather than interpreted (so a stray backslash or percent sign
is typeset, not executed).
"""
from __future__ import annotations

from careeros.domain.resume.achievement import Achievement, AchievementBank, AchievementKind
from careeros.domain.resume.tailoring import AchievementSelection, BulletSelection, TailoringPlan
from careeros.infrastructure.resume.tex_assembler import (
    MARKERS,
    assemble_tex,
    duplicated_markers,
    escape_latex,
    missing_markers,
    render_text,
)

TEMPLATE = f"""\\documentclass{{article}}
\\begin{{document}}
\\section*{{Summary}}
{MARKERS["summary"]}
\\section*{{Skills}}
{MARKERS["skills"]}
\\section*{{Experience}}
{MARKERS["experience"]}
\\section*{{Projects}}
{MARKERS["projects"]}
\\end{{document}}
"""


def _bank() -> AchievementBank:
    return AchievementBank(
        achievements=[
            Achievement(
                id="role-a",
                kind=AchievementKind.EXPERIENCE,
                title="Software Engineer",
                organization="Acme",
                start_date="2024-01",
                end_date="present",
                bullets=["Built APIs.", "Wrote tests."],
                technologies=["python"],
            ),
            Achievement(
                id="project-b",
                kind=AchievementKind.PROJECT,
                title="RAG Tool",
                bullets=["Built a retrieval pipeline."],
                url="https://example.com/repo",
            ),
        ]
    )


def _plan() -> TailoringPlan:
    return TailoringPlan(
        achievements=[
            AchievementSelection("role-a", [BulletSelection(0), BulletSelection(1, rephrased="Added tests.")]),
            AchievementSelection("project-b", [BulletSelection(0)]),
        ],
        skills=["python", "react"],
        summary="Backend engineer.",
    )


class TestEscaping:
    def test_escapes_latex_control_characters(self) -> None:
        assert escape_latex("100% & $5 #1 a_b") == r"100\% \& \$5 \#1 a\_b"

    def test_backslash_is_escaped_without_double_escaping_the_rest(self) -> None:
        # Order matters: escaping "\" after "&" would corrupt the "\&" just produced.
        assert escape_latex(r"C:\path & more") == r"C:\textbackslash{}path \& more"

    def test_braces_are_escaped_so_injected_commands_are_inert(self) -> None:
        assert escape_latex(r"\input{/etc/passwd}") == r"\textbackslash{}input\{/etc/passwd\}"


class TestBoldMarkup:
    """`**bold**` is the only markup bank content may express, so hand-written emphasis survives."""

    def test_bold_markers_become_textbf(self) -> None:
        assert render_text("Built an **AI-powered platform** end to end.") == (
            r"Built an \textbf{AI-powered platform} end to end."
        )

    def test_multiple_bold_spans_are_converted(self) -> None:
        assert render_text("**Frontend** and **backend**.") == r"\textbf{Frontend} and \textbf{backend}."

    def test_percent_inside_bold_is_still_escaped(self) -> None:
        # Escaping runs first, so LaTeX specials remain inert even inside emphasis.
        assert render_text("Cut time by **70%**.") == r"Cut time by \textbf{70\%}."

    def test_latex_injection_inside_bold_stays_inert(self) -> None:
        rendered = render_text(r"**\input{/etc/passwd}**")

        assert r"\input{" not in rendered
        assert r"\textbackslash{}input" in rendered

    def test_unpaired_marker_is_left_alone(self) -> None:
        assert render_text("A ** dangling marker") == "A ** dangling marker"

    def test_text_without_markup_is_unchanged_apart_from_escaping(self) -> None:
        assert render_text("Plain text with 50% margin.") == r"Plain text with 50\% margin."


class TestAssembly:
    def test_template_structure_is_preserved(self) -> None:
        result = assemble_tex(TEMPLATE, _plan(), _bank())

        assert result.startswith("\\documentclass{article}")
        assert "\\end{document}" in result
        assert result.count("\\section*{Experience}") == 1

    def test_every_marker_is_replaced(self) -> None:
        result = assemble_tex(TEMPLATE, _plan(), _bank())

        for marker in MARKERS.values():
            assert marker not in result

    def test_experience_and_projects_land_in_their_own_sections(self) -> None:
        result = assemble_tex(TEMPLATE, _plan(), _bank())
        experience_part = result.split("\\section*{Experience}")[1].split("\\section*{Projects}")[0]
        projects_part = result.split("\\section*{Projects}")[1]

        assert "Software Engineer" in experience_part
        assert "RAG Tool" not in experience_part
        assert "RAG Tool" in projects_part

    def test_reworded_bullet_is_used_and_original_dropped(self) -> None:
        result = assemble_tex(TEMPLATE, _plan(), _bank())

        assert "Added tests." in result
        assert "Wrote tests." not in result

    def test_unselected_bullets_are_omitted(self) -> None:
        plan = TailoringPlan(achievements=[AchievementSelection("role-a", [BulletSelection(0)])])

        result = assemble_tex(TEMPLATE, plan, _bank())

        assert "Built APIs." in result
        assert "Wrote tests." not in result

    def test_metadata_is_rendered_when_present(self) -> None:
        result = assemble_tex(TEMPLATE, _plan(), _bank())

        assert "Acme" in result
        assert "2024-01 -- present" in result
        assert "\\url{https://example.com/repo}" in result

    def test_skills_and_summary_are_rendered(self) -> None:
        result = assemble_tex(TEMPLATE, _plan(), _bank())

        assert "python, react" in result
        assert "Backend engineer." in result

    def test_empty_sections_render_as_blank_rather_than_leaving_markers(self) -> None:
        plan = TailoringPlan(achievements=[AchievementSelection("role-a", [BulletSelection(0)])])

        result = assemble_tex(TEMPLATE, plan, _bank())

        assert MARKERS["projects"] not in result
        assert MARKERS["summary"] not in result


class TestMarkerDiagnostics:
    def test_complete_template_reports_no_missing_markers(self) -> None:
        assert missing_markers(TEMPLATE) == []

    def test_missing_markers_are_reported(self) -> None:
        stripped = TEMPLATE.replace(MARKERS["projects"], "")

        assert missing_markers(stripped) == [MARKERS["projects"]]

    def test_duplicated_markers_are_reported(self) -> None:
        doubled = TEMPLATE + f"\n% docs mention {MARKERS['experience']} here\n"

        assert duplicated_markers(doubled) == [MARKERS["experience"]]

    def test_clean_template_reports_no_duplicates(self) -> None:
        assert duplicated_markers(TEMPLATE) == []

    def test_the_shipped_master_template_has_every_marker_exactly_once(self) -> None:
        # Regression: the header comment originally listed the markers literally, so every section was
        # substituted twice -- and multi-line experience blocks escaped the comment, duplicating a section
        # into the rendered document.
        from careeros.infrastructure.resume.local_tex_resume_source import DEFAULT_MASTER_RESUME_PATH

        content = DEFAULT_MASTER_RESUME_PATH.read_text(encoding="utf-8")

        assert missing_markers(content) == []
        assert duplicated_markers(content) == []
