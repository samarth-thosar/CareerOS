"""FormFiller port -- prepares a job application form for the candidate to review and submit.

Deliberately *prepares*, never submits. Two reasons, and the first is the important one:

1. **The irreversible action stays human.** Submitting an application cannot be undone, and a mis-filled form
   sent to a real employer is worse than no application. This mirrors every other gate in CareerOS -- resume
   tailoring refuses rather than guesses, `apply()` refuses a second submission, email never auto-sends.
2. **Honest posture toward the site.** The browser is the candidate's own, visible, driven on their behalf while
   they watch. That is assistance. Anything built specifically to look human to a bot detector would be
   circumventing a security control, and on some sites also a terms violation with the candidate's account as
   the collateral -- so it is not built here.

`unfilled` matters as much as `filled`: an ATS form routinely has custom questions no generic filler can answer,
and telling the candidate exactly what still needs them is the difference between a useful draft and a
half-finished form they have to audit field by field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class FormFillRequest:
    """Everything needed to draft one application."""

    job_url: str
    answers: dict[str, str]
    resume_pdf_path: str | None = None
    cover_letter: str | None = None


@dataclass(slots=True)
class FormFillResult:
    filled: list[str] = field(default_factory=list)
    unfilled: list[str] = field(default_factory=list)
    resume_attached: bool = False
    cover_letter_attached: bool = False
    left_open_for_review: bool = True
    error: str | None = None

    @property
    def needs_attention(self) -> bool:
        return bool(self.unfilled) or self.error is not None


class FormFiller(Protocol):
    def is_available(self) -> bool: ...
    async def prepare(self, request: FormFillRequest) -> FormFillResult: ...
