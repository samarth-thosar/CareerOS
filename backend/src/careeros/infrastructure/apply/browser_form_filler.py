"""BrowserFormFiller -- drafts application forms as tabs in the candidate's own visible Chrome.

Runs **non-headless on purpose**. The candidate watches it work and presses submit themselves, which is what
makes this assistance rather than an unattended bot: the browser is theirs, the session is theirs, the
irreversible action is theirs. Nothing here tries to look human to a bot detector -- that would be circumventing
a security control, and this deliberately does not do it. Consequently it only works on forms that are not
fighting automation: Greenhouse, Lever and Ashby application pages, which is where every job CareerOS discovers
actually lives.

Two decisions the intended workflow forced, both learned by asking "what do I see when I come back?":

* **One browser, one tab per job.** An earlier version launched a fresh browser per call, so ten jobs meant ten
  Chrome processes -- untenable on a laptop already sharing memory with a local LLM. The browser is now held for
  the process lifetime and tabs are added to it.
* **Never closed on a timer.** That earlier version also closed after fifteen minutes, which would silently
  discard a half-reviewed application. The window stays open until the candidate closes it, or until the app
  shuts down.

Uses `channel="chrome"` to drive the installed browser rather than Playwright's bundled Chromium, because the
Chromium download OOMs on this machine and the installed Chrome works fine.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from careeros.application.ports.form_filler import (
    BatchFormFillResult,
    FormFillRequest,
    FormFillResult,
)

logger = logging.getLogger(__name__)

# A soft ceiling on tabs per batch. Chrome copes with more, but a human reviewing thirty application forms in one
# sitting does not, and each tab holds a form with the candidate's real details in it.
MAX_TABS_PER_BATCH = 12


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
    FieldSpec("portfolio_url", "Portfolio / website", ("input[name*='website']", "input[name*='portfolio']")),
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

# Fields where a form asks for the same fact one of two ways. Reporting the unused variant as "unfilled" is a
# false alarm, and a noisy unfilled list is one the candidate stops reading -- which defeats the point.
_EITHER_OR: dict[str, frozenset[str]] = {
    "Full name": frozenset({"First name", "Last name"}),
    "First name": frozenset({"Full name"}),
    "Last name": frozenset({"Full name"}),
}


class BrowserFormFiller:
    name = "browser"

    def __init__(self, *, headless: bool = False, channel: str = "chrome") -> None:
        # headless=False is the default and the point: the candidate watches and submits.
        self._headless = headless
        self._channel = channel
        # Held for the process lifetime so repeated batches add tabs to one window instead of spawning browsers.
        self._playwright = None
        self._browser = None
        self._context = None

    def is_available(self) -> bool:
        try:
            import playwright  # noqa: F401
        except ImportError:
            return False
        return True

    async def _ensure_browser(self):
        """Start the browser on first use, or reuse it -- including after the candidate closed the window."""
        from playwright.async_api import async_playwright

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._browser is None or not self._browser.is_connected():
            self._browser = await self._playwright.chromium.launch(
                channel=self._channel, headless=self._headless
            )
            self._context = await self._browser.new_context(accept_downloads=True)
        return self._context

    async def prepare(self, requests: list[FormFillRequest]) -> BatchFormFillResult:
        batch = BatchFormFillResult()
        if not requests:
            return batch

        if not self.is_available():
            batch.skipped = [
                FormFillResult(job_id=r.job_id, job_title=r.job_title, company_name=r.company_name,
                               error="Playwright is not installed")
                for r in requests
            ]
            return batch

        queued, overflow = requests[:MAX_TABS_PER_BATCH], requests[MAX_TABS_PER_BATCH:]
        for request in overflow:
            batch.skipped.append(
                FormFillResult(
                    job_id=request.job_id,
                    job_title=request.job_title,
                    company_name=request.company_name,
                    error=f"Not opened — batch limit is {MAX_TABS_PER_BATCH} tabs. Run again for the rest.",
                )
            )

        try:
            context = await self._ensure_browser()
        except Exception as error:  # noqa: BLE001
            logger.exception("Could not start the browser")
            batch.skipped.extend(
                FormFillResult(job_id=r.job_id, job_title=r.job_title, company_name=r.company_name,
                               error=f"{type(error).__name__}: {error}")
                for r in queued
            )
            return batch

        for request in queued:
            result = await self._prepare_one(context, request)
            (batch.skipped if result.error else batch.prepared).append(result)

        batch.tabs_open = len(context.pages)
        # Never closed here: the candidate reviews and submits in their own time, then closes the window.
        batch.browser_left_open = True
        logger.info("Prepared %d forms across %d tabs", len(batch.prepared), batch.tabs_open)
        return batch

    async def _prepare_one(self, context, request: FormFillRequest) -> FormFillResult:
        result = FormFillResult(
            job_id=request.job_id, job_title=request.job_title, company_name=request.company_name
        )
        try:
            page = await context.new_page()
            await page.goto(request.job_url, wait_until="domcontentloaded", timeout=60_000)
            # Many ATS pages put the form behind an "Apply" button rather than showing it inline.
            await self._reveal_form(page)

            await self._fill_text_fields(page, request, result)
            await self._attach_resume(page, request, result)
            await self._fill_cover_letter(page, request, result)
        except Exception as error:  # noqa: BLE001 - one bad form must not abandon the rest of the batch
            logger.exception("Could not prepare %s", request.job_url)
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

    async def close(self) -> None:
        """Shut the browser down. Called on app shutdown, never mid-review."""
        try:
            if self._browser is not None and self._browser.is_connected():
                await self._browser.close()
        finally:
            self._browser = None
            self._context = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None


def _prune_satisfied_alternatives(result: FormFillResult) -> None:
    filled = set(result.filled)
    result.unfilled = [
        label for label in result.unfilled if not (label in _EITHER_OR and _EITHER_OR[label] <= filled)
    ]
