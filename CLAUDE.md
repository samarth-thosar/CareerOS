# CareerOS — working notes

Personal career operating system: discovers jobs, scores them against a profile, tailors resumes, tracks
applications. Single user, runs locally, **zero paid services**.

## Run it

```bash
# Backend (:8000)
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn careeros.presentation.api.app:create_app --factory --port 8000
#   ...or: .venv/Scripts/python.exe scripts/serve.py

# Frontend (:3000)
cd frontend && npm run dev

# Tests — ALWAYS use -m "not slow" while iterating (the slow ones invoke a real LaTeX engine)
cd backend && .venv/Scripts/python.exe -m pytest -q -m "not slow"     # 255 tests, ~8s
```

First run needs data: `POST /profile/reload`, then `POST /jobs/discover`, then `POST /scoring/run?limit=N`.

## Known environment traps

**A wedged WMI service (this machine, currently).** `import sqlalchemy` hangs, and so do alembic, uvicorn and
every integration test — while httpx/pydantic/fastapi import fine. Cause: SQLAlchemy imports `platform`, whose
`uname()` queries WMI on Windows. `Get-CimInstance`, `tasklist` and `taskkill` hang for the same reason.
Worked around by `.venv/Lib/site-packages/sitecustomize.py` (gitignored) seeding `platform._uname_cache`.
**Real fix: `net stop winmgmt && net start winmgmt` as admin, or reboot — then delete that file and
`backend/scripts/wmi_workaround.py`.** If diagnosing something similar: `platform.release()` and
`platform.version()` also route through `uname()`, so they cannot be used inside the workaround.

**Set `CAREEROS_SCHEDULER__ENABLED=false` while working interactively.** One Ollama instance serialises
generation, so a scheduled 20-job scoring batch queues ahead of an interactive tailoring request and times it
out. Leaving the backend running unattended also reloads qwen3 every 15 min and can saturate the machine.

**Scoring is slow: ~40s/job.** 218 unscored ≈ 2.5h. Batches are bounded and resumable by design; the queue is
"jobs with no Score row", which survives restarts.

**Playwright browsers aren't installed** (download failed, OOM). Declared for future scraping but unused —
current discovery is a JSON API.

## Architecture (see docs/architecture/)

Clean architecture, dependencies inward: `domain` (no framework imports) ← `application` (services + ports) ←
`infrastructure` (adapters) / `presentation` (FastAPI). `infrastructure/bootstrap.py` is the composition root
and the map of the system — manual DI, no framework.

**Events.** Services publish to a per-unit-of-work `DeferredEventBus`, drained onto the process-wide bus only
**after commit**. This is load-bearing: publishing mid-transaction announced facts a rollback could erase, and
made subscribers contend with the publisher's write lock (SQLite reports that as "database is locked").
Handlers each get their own transaction, so they must be idempotent.

**12 events exist; 4 have subscribers** (`JobDiscovered`, `JobScored`, `ResumeGenerated`,
`CoverLetterGenerated`). `ResumeGenerated` -> `attach_resume` is load-bearing: `Application.apply()` only
permits submission from `resume_generated`, so without it every application would be unsubmittable.

**Read models** (`persistence/read_models.py`, `analytics_read_model.py`) bypass aggregates for queries —
light CQRS. Repositories rebuild aggregates for writes.

## Location / work authorisation (load-bearing)

The candidate can work **in India only** — Pune and Bangalore preferred, Mumbai a distant third, remote-in-India
fine. No US work permit. `domain/job/location_eligibility.py` filters ineligible postings at the source, before
they reach the database or cost an LLM call.

It is an **allowlist, deliberately**. A blocklist of ineligible countries was tried first and leaked Norway,
Greece and Romania, because no hand-written country list is ever complete. The question is "does this name a
place I can work in?", so an unfamiliar location fails closed.

Two traps: **`remote_type == REMOTE` does not mean "anyone may apply"** — "US Remote" and "Remote (US/Canada)"
are region-locked, and treating remote as open is the most expensive mistake here. And **never put `remote` in
`eligible_locations`**: "US Remote" contains it, which would re-admit every US role.

`Location.raw` is the source of truth. `city`/`country` are populated only for single-location postings, because
Greenhouse writes "New York, San Francisco, Seattle, or Remote (US/Canada)" in one field and guessing one pair
from that produced city="San Francisco", country="WA".

**Board slugs are not company names.** A hand-written Greenhouse list had 14 of 17 404. Every slug in
`config/default.yaml` was verified by probing the API; re-probe before adding more (a bad slug is silently
skipped, so it costs nothing and yields nothing).

**Three sources, all free public APIs, no scraping:** Greenhouse
(`boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true`), Lever
(`api.lever.co/v0/postings/<slug>?mode=json`), Ashby
(`api.ashbyhq.com/posting-api/job-board/<slug>`). None has cross-company search, so companies are named in
config. Payload shapes differ: Lever puts the title in `text`, the location in `categories.location`, and
timestamps in epoch millis; Ashby exposes `isListed`, and unlisted postings are skipped since they cannot be
applied to.

**Wellfound is not viable and this was checked, not assumed.** It sits behind Cloudflare bot protection — a
filtered listing URL returns 403, and even pages that load block on a second request — publishes no API, gates
most listings behind a login, and forbids scraping. Lever and Ashby cover the same startup postings through
documented endpoints. Don't spend time on Wellfound without a logged-in browser session, and note that route
violates their terms.

## Applying

The user's model: **CareerOS lists, the user picks, CareerOS applies.** Selection is always explicit — the
system never chooses which jobs to apply to. `ApplicationSubmissionService` refuses a batch unless every
required answer in `config/application_answers.yaml` is filled (no invented notice period reaches a real
employer), a tailored resume exists, and the job was never applied to before.

No source supports automated submission yet (`supports_auto_submit` is False everywhere), so submissions report
`needs_manual_step` with the form URL rather than pretending. `POST /applications/{job_id}/confirm-applied`
records a manually submitted form so the never-apply-twice guard and outcome metrics stay correct.

## Non-negotiable product rules

- **Never fabricate resume content.** Tailoring only *selects* achievement ids from `data/master/achievements.yaml`
  and may reword existing bullets. `domain/resume/tailoring.py::validate_plan` rejects unknown ids, unknown
  bullet indices, unclaimed skills, and **any reworded bullet containing a figure absent from the original**
  (invented metrics). A refused plan writes nothing — surface the message, it tells the user what to add.
- **Never overwrite a resume version.** Each run adds a `ResumeVersion` and a new artifact folder (`-2`, `-3`…).
- **Never apply twice.** Enforced three ways: `Application.apply()` checks `applied_at`, a DB unique constraint
  on `job_id`, and a re-check before submission.
- **Never auto-send email.** `EmailMessage.sent_at` stays null until an explicit approval gate.

## Conventions

- Type hints everywhere; docstrings explain **why**, not what.
- Tests: `tests/unit` (pure, fast) → `tests/fakes` for every port → `tests/integration` (real SQLite).
  **Integration tests must not depend on the user's own data** — use fixture banks/profiles, not
  `data/master/*` or `config/profile.yaml`.
- The LLM is swappable: build a model-agnostic `PromptSpec`; all model quirks live in the adapter
  (`infrastructure/llm/ollama_provider.py` handles thinking-mode and JSON recovery).
- `PromptSpec.max_output_tokens` is per-prompt — a global cap silently truncated tailoring into unparseable JSON.
- Dashboard colour: score is a **magnitude** → one sequential blue ramp, length encodes value. Application state
  → reserved status palette, always with a text label. Re-step ramps with the dataviz validator, never by eye.

## Files that hold user content (placeholders replaced with real data)

| File | What |
|---|---|
| `backend/config/profile.yaml` | Skills, role priorities, preferences. `years_experience: 2` is a judgment call worth confirming. |
| `backend/data/master/resume.tex` | Real resume + 4 `%%CAREEROS:*%%` markers. Each must appear **exactly once** — a marker inside a comment gets substituted too, and multi-line blocks then escape the comment. |
| `backend/data/master/achievements.yaml` | The honesty ceiling for generated resumes. Bullets use block scalars (`>-`): plain scalars break on `word: **bold**`. |
| `backend/config/application_answers.yaml` | Notice period, expected CTC, work authorisation. `TODO` blocks submission by design. Editable at `/profile`. |
| `backend/data/master/voice.md` | Cover-letter voice and angle. Shapes framing only — facts still come from the achievement bank. |
| `backend/.env` | Gitignored. Holds the Tectonic path. |
| `resume-current.tex` | Untouched original, repo root. |

## Status

Done: architecture, discovery (Greenhouse, India-filtered), scoring, resume tailoring + PDF, cover letters,
dashboard (shortlist/pipeline/insights/gaps/profile), select-and-apply flow with tracking.
Pending: **automated form submission** (needs per-source browser automation; everything up to the submit button
works), email/rejection detection, WhatsApp, memory, company intelligence, more job sources (Wellfound blocked — see above),
Overleaf sync.
