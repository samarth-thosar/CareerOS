# CareerOS

A personal AI career operating system -- not a job-application bot. CareerOS is meant to grow into an AI
executive assistant dedicated to one person's job search: discovering jobs, scoring them against a resume,
tailoring resumes and cover letters, tracking applications end to end, and eventually monitoring recruiter
email and notifying over WhatsApp, all behind a dashboard.

This repository is at **Phase 1**: architecture and a runnable skeleton. There is no feature logic yet --
no real job scraping, LLM prompting, resume tailoring, or dashboard. See
[docs/architecture/](docs/architecture/) for the full design, and the phase roadmap below for what's next.

Every component defaults to a free or local option -- see
[docs/architecture/decisions/0005-zero-paid-services-constraint.md](docs/architecture/decisions/0005-zero-paid-services-constraint.md).

## Architecture

Start with [docs/architecture/00-overview.md](docs/architecture/00-overview.md). In short: a clean
architecture (domain -> application -> infrastructure -> presentation, dependencies pointing inward),
async-first (FastAPI, async SQLAlchemy, Playwright's async API), modules communicating through an in-process
domain event bus, dependency injection via a single manual composition root, and layered YAML + `.env`
configuration.

## Running it

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
playwright install chromium  # only needed once real scraping lands in Phase 4

copy .env.example .env       # macOS/Linux: cp .env.example .env

alembic upgrade head          # creates the SQLite schema
pytest                         # domain unit tests + the health-endpoint integration test
uvicorn careeros.presentation.api.app:create_app --factory --reload
```

`GET http://localhost:8000/health` should return `{"status": "ok"}` once the server is running -- this does
a real round trip through the database, not a hardcoded response.

Ollama is required for scoring and resume tailoring. Pull the default model once with `ollama pull qwen3:8b`;
the app boots and the test suite passes without it, since tests use a scripted model rather than a real one.

### PDF rendering (optional)

Tailoring always writes `resume.tex`. Compiling it to PDF needs a LaTeX engine — any of `tectonic`,
`pdflatex`, `xelatex` or `lualatex` on `PATH` is detected automatically. Tectonic is the lightest option: a
single ~50MB binary that downloads only the packages a document actually uses.

```bash
# Windows: grab the release binary and put it somewhere on PATH
curl -L -o tectonic.zip https://github.com/tectonic-typesetting/tectonic/releases/latest/download/tectonic-0.17.0-x86_64-pc-windows-msvc.zip
# macOS/Linux: brew install tectonic  |  cargo install tectonic
```

With no engine installed nothing breaks — tailoring reports `pdf_unavailable` and still produces the `.tex`.
If an engine is installed but a long-running shell or IDE has not picked up the `PATH` change, set
`CAREEROS_RESUME__LATEX_ENGINE` in `.env` to its absolute path.

### Frontend

```bash
cd frontend
npm install
copy .env.local.example .env.local   # macOS/Linux: cp .env.local.example .env.local
npm run dev
```

Visit `http://localhost:3000` -- the page calls the backend's `/health` endpoint and shows the result,
proving the two apps are wired together. The real dashboard starts at Phase 8.

### Everything together, via Docker

```bash
docker compose up --build
```

Brings up the backend and a local Ollama instance. No cloud services, no paid tiers.

## Phase roadmap

- **Phase 1 -- Architecture + runnable skeleton** (this phase): clean architecture, ports, domain model,
  event catalog, docs, and a booting app with no feature logic.
- **Phase 4 -- Job Discovery**: real `JobSourceProvider` adapters (Wellfound first), scraping and
  de-duplication.
- **Phase 5 -- Company Intelligence**: enrichment from Discovery/Email/Application events.
- **Phase 6 -- Job Scoring**: real LLM-backed scoring against the candidate profile.
- **Phase 7 -- Resume Manager**: Overleaf sync, tailoring, gap-flagging, PDF rendering, cover letters.
- **Phase 8 -- Dashboard**: the real frontend, beyond the wiring-check page.
- **Phase 9 -- Application Tracker**: the full event-reacting lifecycle service.
- **Phase 10 -- Email Agent**: Gmail integration, classification, draft replies (never auto-sent).
- **Phase 11 -- WhatsApp Agent**: notifications and inbound commands (adapter choice made explicitly at
  this phase; see [ADR-0005](docs/architecture/decisions/0005-zero-paid-services-constraint.md)).
- **Phase 12 -- Memory**: outcome correlation and suggested (never auto-applied) scoring-weight changes.

Phases 2 and 3 (folder structure, project initialization) are folded into this phase's runnable skeleton.
Each remaining phase lands with its own explanation of design decisions, tests, and a review gate before the
next one starts.
