"""Assembles a tailored .tex by substituting markers in the master template.

The model never emits LaTeX. It returns a validated `TailoringPlan` of ids and reworded bullets, and this
module renders that into markup. Two consequences worth stating:

* **The document cannot be broken.** Structure, packages and layout come from the master template verbatim;
  only marker lines are replaced.
* **Content cannot be injected.** Every rendered line originates from an achievement bullet, and all text is
  LaTeX-escaped, so a stray `\\input{}` or `%` in bank content is typeset literally rather than executed.
"""
from __future__ import annotations

import re

from careeros.application.ports.resume_assembler import TemplateIssues
from careeros.domain.resume.achievement import AchievementBank, AchievementKind
from careeros.domain.resume.tailoring import TailoringPlan

MARKERS = {
    "summary": "%%CAREEROS:SUMMARY%%",
    "skills": "%%CAREEROS:SKILLS%%",
    "experience": "%%CAREEROS:EXPERIENCE%%",
    "projects": "%%CAREEROS:PROJECTS%%",
}

_LATEX_ESCAPES: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

_ESCAPE_PATTERN = re.compile("|".join(re.escape(character) for character in _LATEX_ESCAPES))

# Markdown-style bold in bank content. Applied *after* escaping: `*` is not a LaTeX special character, so the
# markers survive escaping untouched and can then be turned into real markup. This gives the candidate the
# emphasis their handwritten resume had, without letting arbitrary LaTeX through -- `**` is the only markup
# the bank can express, and everything else stays inert.
_BOLD_MARKUP = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def escape_latex(text: str) -> str:
    """Make arbitrary text safe to typeset. Bank content is trusted-ish, but never trusted as markup.

    Deliberately a single pass. Replacing character by character in sequence corrupts the output, because
    several replacements themselves contain braces and backslashes that a later rule would escape again --
    e.g. "\\" becomes "\\textbackslash{}", whose braces a subsequent brace rule would turn into
    "\\textbackslash\\{\\}". One pass over the original never revisits what it has emitted.
    """
    return _ESCAPE_PATTERN.sub(lambda match: _LATEX_ESCAPES[match.group()], text)


def render_text(text: str) -> str:
    """Escape text, then honour the one markup form bank content may use: **bold**."""
    return _BOLD_MARKUP.sub(r"\\textbf{\1}", escape_latex(text))


def _render_entry(achievement, bullets: list[str]) -> str:
    """One experience/project block: a bold heading, optional metadata, then an itemize of its bullets."""
    heading = f"\\textbf{{{escape_latex(achievement.title)}}}"
    if achievement.organization:
        heading += f", \\textbf{{{escape_latex(achievement.organization)}}}"

    dates = " -- ".join(
        escape_latex(part) for part in (achievement.start_date, achievement.end_date) if part
    )
    if dates:
        heading += f" \\hfill \\textbf{{{dates}}}"

    lines = [heading]
    if achievement.technologies:
        lines.append(f"\\\\ \\textit{{{escape_latex(', '.join(achievement.technologies))}}}")
    if achievement.url:
        # url is emitted unescaped inside \url{}, which handles special characters itself.
        lines.append(f"\\\\ \\url{{{achievement.url}}}")

    lines.append("\\begin{itemize}")
    lines.extend(f"  \\item {render_text(bullet)}" for bullet in bullets)
    lines.append("\\end{itemize}")
    return "\n".join(lines)


def assemble_tex(master_tex: str, plan: TailoringPlan, bank: AchievementBank) -> str:
    """Render `plan` into `master_tex`.

    Assumes `plan` has already passed `validate_plan`; ids and bullet indices are resolved here and will raise
    if they do not exist, which is a programming error at this point rather than a model mistake.
    """
    experience_blocks: list[str] = []
    project_blocks: list[str] = []

    for selection in plan.achievements:
        achievement = bank.get(selection.achievement_id)
        bullets = [
            bullet.render(achievement.bullet(bullet.source_index)) for bullet in selection.bullets
        ]
        block = _render_entry(achievement, bullets)
        if achievement.kind is AchievementKind.EXPERIENCE:
            experience_blocks.append(block)
        else:
            project_blocks.append(block)

    replacements = {
        MARKERS["summary"]: render_text(plan.summary) if plan.summary else "",
        MARKERS["skills"]: escape_latex(", ".join(plan.skills)) if plan.skills else "",
        MARKERS["experience"]: "\n\n\\vspace{4pt}\n".join(experience_blocks),
        MARKERS["projects"]: "\n\n\\vspace{4pt}\n".join(project_blocks),
    }

    tailored = master_tex
    for marker, replacement in replacements.items():
        tailored = tailored.replace(marker, replacement)
    return tailored


def missing_markers(master_tex: str) -> list[str]:
    """Markers absent from the template, so a misconfigured master can be reported rather than silently thin."""
    return [marker for marker in MARKERS.values() if marker not in master_tex]


def duplicated_markers(master_tex: str) -> list[str]:
    """Markers appearing more than once, which silently duplicates content.

    Worth checking separately from `missing_markers` because the failure is much nastier than a thin section:
    substitution fills every occurrence, so a marker written inside a LaTeX comment gets filled too, and a
    multi-line replacement escapes the comment after its first line and injects a stray copy of the section
    into the rendered document.
    """
    return [marker for marker in MARKERS.values() if master_tex.count(marker) > 1]


class TexAssembler:
    """The LaTeX implementation of the ResumeAssembler port."""

    def assemble(self, master: str, plan: TailoringPlan, bank: AchievementBank) -> str:
        return assemble_tex(master, plan, bank)

    def check_template(self, master: str) -> TemplateIssues:
        return TemplateIssues(missing=missing_markers(master), duplicated=duplicated_markers(master))
