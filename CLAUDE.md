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

**Don't leave the backend running unattended.** Its scheduler fires a scoring batch every 15 min — 20 jobs ×
~40s of local inference — which reloads qwen3 and can saturate the machine.

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

**12 events exist; only `JobDiscovered` and `JobScored` have subscribers.** Known gap: `ResumeGenerated` has
none, so tailoring a resume does not advance the application to `resume_generated`.

**Read models** (`persistence/read_models.py`, `analytics_read_model.py`) bypass aggregates for queries —
light CQRS. Repositories rebuild aggregates for writes.

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
| `backend/.env` | Gitignored. Holds the Tectonic path. |
| `resume-current.tex` | Untouched original, repo root. |

## Status

Done: architecture, discovery (Greenhouse), scoring, resume tailoring + PDF (Tectonic), dashboard.
Pending: **applying** (the big one — user selects from the list, system submits), cover letters, tracker states
beyond `interested`, email/rejection detection, WhatsApp, memory, company intelligence, more job sources
(Wellfound not yet built), Overleaf sync.
