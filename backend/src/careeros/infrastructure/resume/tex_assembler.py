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


def escape_latex(text: str) -> str:
    """Make arbitrary text safe to typeset. Bank content is trusted-ish, but never trusted as markup.

    Deliberately a single pass. Replacing character by character in sequence corrupts the output, because
    several replacements themselves contain braces and backslashes that a later rule would escape again --
    e.g. "\\" becomes "\\textbackslash{}", whose braces a subsequent brace rule would turn into
    "\\textbackslash\\{\\}". One pass over the original never revisits what it has emitted.
    """
    return _ESCAPE_PATTERN.sub(lambda match: _LATEX_ESCAPES[match.group()], text)


def _render_entry(achievement, bullets: list[str]) -> str:
    """One experience/project block: a bold heading, optional metadata, then an itemize of its bullets."""
    heading = f"\\textbf{{{escape_latex(achievement.title)}}}"
    if achievement.organization:
        heading += f", {escape_latex(achievement.organization)}"

    dates = " -- ".join(
        escape_latex(part) for part in (achievement.start_date, achievement.end_date) if part
    )
    if dates:
        heading += f" \\hfill {dates}"

    lines = [heading + " \\\\"]
    if achievement.technologies:
        lines.append(f"\\textit{{{escape_latex(', '.join(achievement.technologies))}}} \\\\")
    if achievement.url:
        # url is emitted unescaped inside \url{}, which handles special characters itself.
        lines.append(f"\\url{{{achievement.url}}} \\\\")

    lines.append("\\begin{itemize}")
    lines.extend(f"  \\item {escape_latex(bullet)}" for bullet in bullets)
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
        MARKERS["summary"]: escape_latex(plan.summary) if plan.summary else "",
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
