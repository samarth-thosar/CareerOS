"""BrowserFormFiller -- drafts an application form in the candidate's own visible Chrome.

Runs **non-headless on purpose**. The candidate watches it work and presses submit themselves, which is what
makes this assistance rather than an unattended bot: the browser is theirs, the session is theirs, the
irreversible action is theirs. Nothing here tries to look human to a bot detector -- that would be
circumventing a security control, and this deliberately does not do it. Consequently it only works on forms
that are not fighting automation: Greenhouse, Lever and Ashby application pages, which is where every job
CareerOS discovers actually lives.

Uses `channel="chrome"` to drive the installed browser instead of Playwright's bundled Chromium, because the
Chromium download OOMs on this machine and the installed Chrome works fine.

Field matching is best-effort and reports what it could not fill. ATS forms carry arbitrary custom questions,
and pretending to have completed one would be worse than naming it -- so `unfilled` is a first-class result.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from careeros.application.ports.form_filler import FormFillRequest, FormFillResult

logger = logging.getLogger(__name__)

# How long to leave the window open for the candidate to review and submit. Generous: reading a job form and
# deciding to send it is not a five-second task.
_REVIEW_WINDOW_MS = 15 * 60 * 1000


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One logical field and the selectors ATS forms actually use for it, most specific first."""

    answer_key: str
    label: str
    selectors: tuple[str, ...]


# Ordered most-reliable-first. Greenhouse uses `id="first_name"`-style ids, Lever uses `name="name"`, Ashby uses
# label text -- so each field lists several strategies rather than assuming one vendor.
FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("full_name", "Full name", ("input#name", "input[name='name']", "input[autocomplete='name']")),
    FieldSpec("first_name", "First name", ("input#first_name", "input[name='first_name']", "input[name*='first']")),
    FieldSpec("last_name", "Last name", ("input#last_name", "input[name='last_name']", "input[name*='last']")),
    FieldSpec("email", "Email", ("input#email", "input[type='email']", "input[name*='email']")),
    FieldSpec("phone", "Phone", ("input#phone", "input[type='tel']", "input[name*='phone']")),
    FieldSpec(
        "linkedin_url",
        "LinkedIn",
        ("input[name*='linkedin']", "input[id*='linkedin']", "input[aria-label*='LinkedIn' i]"),
    ),
    FieldSpec(
        "github_url",
        "GitHub",
        ("input[name*='github']", "input[id*='github']", "input[aria-label*='GitHub' i]"),
    ),
    FieldSpec(
        "current_location",
        "Location",
        ("input[name*='location']", "input#location", "input[aria-label*='location' i]"),
    ),
    FieldSpec(
        "portfolio_url",
        "Portfolio / website",
        ("input[name*='website']", "input[name*='portfolio']"),
    ),
)

_RESUME_SELECTORS = (
    "input[type='file'][name*='resume']",
    "input[type='file'][id*='resume']",
    "input[type='file']",
)

_COVER_LETTER_SELECTORS = (
    "textarea[name*='cover']",
    "textarea[id*='cover']",
    "textarea[aria-label*='cover' i]",
    "textarea",
)


class BrowserFormFiller:
    name = "browser"

    def __init__(self, *, headless: bool = False, channel: str = "chrome") -> None:
        # headless=False is the default and the point: the candidate watches and submits.
        self._headless = headless
        self._channel = channel

    def is_available(self) -> bool:
        try:
            import playwright  # noqa: F401
        except ImportError:
            return False
        return True

    async def prepare(self, request: FormFillRequest) -> FormFillResult:
        if not self.is_available():
            return FormFillResult(error="Playwright is not installed", left_open_for_review=False)

        from playwright.async_api import async_playwright

        result = FormFillResult()
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(channel=self._channel, headless=self._headless)
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(request.job_url, wait_until="domcontentloaded", timeout=60_000)

                # Many ATS pages put the form behind an "Apply" button rather than showing it inline.
                await self._reveal_form(page)

                await self._fill_text_fields(page, request, result)
                await self._attach_resume(page, request, result)
                await self._fill_cover_letter(page, request, result)

                logger.info(
                    "Prepared %s: filled %s; still needs %s",
                    request.job_url, result.filled, result.unfilled or "nothing",
                )

                if self._headless:
                    await browser.close()
                    result.left_open_for_review = False
                else:
                    # Left open on purpose: the candidate reviews and presses submit. Never clicked here.
                    await page.wait_for_timeout(_REVIEW_WINDOW_MS)
                    await browser.close()
        except Exception as error:  # noqa: BLE001 - report any browser failure rather than crashing the request
            logger.exception("Could not prepare the form at %s", request.job_url)
            result.error = f"{type(error).__name__}: {error}"

        return result

    async def _reveal_form(self, page) -> None:
        """Click through to the form if the page shows a call-to-action first. Harmless when already visible."""
        for selector in ("text=/^Apply( for this job)?$/i", "a[href*='#app']", "button:has-text('Apply')"):
            try:
                element = page.locator(selector).first
                if await element.count() and await element.is_visible():
                    await element.click(timeout=5_000)
                    await page.wait_for_timeout(1_500)
                    return
            except Exception:
                continue

    async def _fill_text_fields(self, page, request: FormFillRequest, result: FormFillResult) -> None:
        for spec in FIELDS:
            value = request.answers.get(spec.answer_key, "").strip()
            if not value:
                continue
            if await self._try_fill(page, spec.selectors, value):
                result.filled.append(spec.label)
            else:
                result.unfilled.append(spec.label)

        _prune_satisfied_alternatives(result)

    async def _try_fill(self, page, selectors: tuple[str, ...], value: str) -> bool:
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if not await element.count() or not await element.is_editable(timeout=2_000):
                    continue
                await element.fill(value, timeout=5_000)
                return True
            except Exception:
                continue
        return False

    async def _attach_resume(self, page, request: FormFillRequest, result: FormFillResult) -> None:
        if not request.resume_pdf_path:
            result.unfilled.append("Resume (no PDF generated yet)")
            return
        for selector in _RESUME_SELECTORS:
            try:
                element = page.locator(selector).first
                if not await element.count():
                    continue
                await element.set_input_files(request.resume_pdf_path, timeout=10_000)
                result.resume_attached = True
                result.filled.append("Resume PDF")
                return
            except Exception:
                continue
        result.unfilled.append("Resume upload")

    async def _fill_cover_letter(self, page, request: FormFillRequest, result: FormFillResult) -> None:
        if not request.cover_letter:
            return
        if await self._try_fill(page, _COVER_LETTER_SELECTORS, request.cover_letter):
            result.cover_letter_attached = True
            result.filled.append("Cover letter")
        else:
            result.unfilled.append("Cover letter")


# Fields where the form asks for the same fact one of two ways. Reporting the unused variant as "unfilled" is a
# false alarm, and a noisy unfilled list is one the candidate stops reading -- which defeats the point of having
# it. Key is the label to drop; value is the set of labels that, together, already cover it.
_EITHER_OR: dict[str, frozenset[str]] = {
    "Full name": frozenset({"First name", "Last name"}),
    "First name": frozenset({"Full name"}),
    "Last name": frozenset({"Full name"}),
}


def _prune_satisfied_alternatives(result: FormFillResult) -> None:
    filled = set(result.filled)
    result.unfilled = [
        label
        for label in result.unfilled
        if not (label in _EITHER_OR and _EITHER_OR[label] <= filled)
    ]
