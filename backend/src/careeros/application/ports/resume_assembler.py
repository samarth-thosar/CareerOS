"""ResumeAssembler port -- renders a validated tailoring plan into a resume document.

An object rather than a bare function because assembling and validating the template are two halves of the
same concern: whoever knows how to substitute into a template is also the only thing that knows what a
well-formed template looks like. Keeping both behind this port lets the document format change (LaTeX today,
Markdown or HTML later) without ResumeManagerService learning anything about markup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from careeros.domain.resume.achievement import AchievementBank
from careeros.domain.resume.tailoring import TailoringPlan


@dataclass(slots=True)
class TemplateIssues:
    """Problems found in a master template.

    Duplicates are tracked separately from missing markers because the consequences differ sharply: a missing
    marker leaves a section empty, whereas a duplicated one fills every occurrence -- and a multi-line block
    substituted inside a comment escapes that comment after its first line, injecting a stray section into the
    rendered document.
    """

    missing: list[str] = field(default_factory=list)
    duplicated: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.duplicated


class ResumeAssembler(Protocol):
    def assemble(self, master: str, plan: TailoringPlan, bank: AchievementBank) -> str: ...
    def check_template(self, master: str) -> TemplateIssues: ...
