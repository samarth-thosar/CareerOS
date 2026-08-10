"""FormFiller port -- prepares job application forms for the candidate to review and submit.

Deliberately *prepares*, never submits. Two reasons, and the first is the important one:

1. **The irreversible action stays human.** Submitting an application cannot be undone, and a mis-filled form
   sent to a real employer is worse than no application. This mirrors every other gate in CareerOS -- resume
   tailoring refuses rather than guesses, `apply()` refuses a second submission, email never auto-sends.
2. **Honest posture toward the site.** The browser is the candidate's own, visible, driven on their behalf while
   they watch. That is assistance. Anything built specifically to look human to a bot detector would be
   circumventing a security control, and on some sites also a terms violation with the candidate's account as
   the collateral -- so it is not built here.

**Batch-shaped, and open-ended.** The real workflow is "queue up several, come back, review them together", so
`prepare` takes many requests and opens one tab per job in a single browser. One browser with N tabs rather than
N browsers matters on a laptop; and the window is never closed on a timer, because a timeout that discards a
half-reviewed application is worse than one left open.

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

    job_id: str
    job_title: str
    company_name: str
    job_url: str
    answers: dict[str, str]
    resume_pdf_path: str | None = None
    cover_letter: str | None = None


@dataclass(slots=True)
class FormFillResult:
    job_id: str
    job_title: str = ""
    company_name: str = ""
    filled: list[str] = field(default_factory=list)
    unfilled: list[str] = field(default_factory=list)
    resume_attached: bool = False
    cover_letter_attached: bool = False
    error: str | None = None

    @property
    def needs_attention(self) -> bool:
        return bool(self.unfilled) or self.error is not None


@dataclass(slots=True)
class BatchFormFillResult:
    prepared: list[FormFillResult] = field(default_factory=list)
    skipped: list[FormFillResult] = field(default_factory=list)
    tabs_open: int = 0
    browser_left_open: bool = False

    @property
    def counts(self) -> dict[str, int]:
        return {"prepared": len(self.prepared), "skipped": len(self.skipped), "tabs_open": self.tabs_open}


class FormFiller(Protocol):
    def is_available(self) -> bool: ...
    async def prepare(self, requests: list[FormFillRequest]) -> BatchFormFillResult: ...
    async def close(self) -> None: ...
