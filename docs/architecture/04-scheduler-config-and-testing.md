# CareerOS Architecture — Scheduler, Configuration, and Cross-Cutting Concerns

## Scheduler design

`SchedulerPort` is the seam. Phase-1 adapter: `APSchedulerAdapter` wrapping `AsyncIOScheduler`, using its
SQLAlchemy jobstore against the same SQLite file so scheduled cycles survive restarts without duplicate
firing. Each scheduled job body is a thin wrapper: open a unit of work, resolve the target application
service from the container, invoke it, catch/log exceptions (a failed discovery cycle must never crash the
scheduler), and use `max_instances=1` per job id so a slow Playwright-based cycle can't overlap itself.

Registered jobs (as they come online): one discovery cycle per enabled provider (staggered), nightly Memory
recomputation, and placeholders for future email polling and master-resume sync.

**Migration seam to Celery/Redis.** Application services are invoked only via `SchedulerPort` — never via
direct APScheduler calls in service code — so swapping later means writing a `CeleryAdapter` that satisfies
the same protocol (its task body resolves the same service from the container inside a worker process) and
swapping the `EventBus` adapter for a Redis-backed one. No publisher/service code changes; only
composition-root wiring changes. This is the concrete payoff of the manual-DI decision (ADR-0003).

Because APScheduler runs in the same event loop as FastAPI, browser automation must use Playwright's async
API correctly (proper `await`s) so long scrapes don't block the loop — an implementation-phase concern,
noted here so it isn't forgotten once Phase 4 starts.

## Configuration strategy

`pydantic-settings`, precedence **env > YAML > code defaults**.

- **YAML** (`backend/config/default.yaml`) holds domain tunables: scoring weights, enabled providers,
  LLM provider/model choice, feature flags (`auto_apply_enabled`, `auto_tailor_resume`, notification
  batching window).
- **`.env`** / environment variables hold secrets: LLM base URL, and future WhatsApp/Gmail/Overleaf
  credentials when those integrations are built.

The composition root is the only place that touches the `Settings` object directly — it hands narrow typed
slices (e.g. a `ScoringWeights` value object) to services, so domain/application code never imports
`pydantic-settings` or knows how configuration is loaded.

## Structured logging

JSON logs (`structlog`), with a `correlation_id` generated at the point an event chain originates (a
discovery-cycle id, or an inbound WhatsApp command id) and carried in every `DomainEvent`'s envelope — this
is necessary because event-bus fan-out breaks the normal single-stack-trace tracing you get from direct
calls. LLM prompt/response detail logs at `DEBUG` (secrets redacted); lifecycle transitions at `INFO`;
handler exceptions at `ERROR` with event name + aggregate id. Score explanations and resume diffs are
persisted as domain data, not just logged, since they need to be inspectable independent of log retention.

## Testing strategy (four tiers)

1. **Domain** — pure synchronous unit tests, no fakes needed (zero dependencies). Exhaustively test the
   `Application` transition table, `ResumeVersion` immutability, `Job` dedupe key, `Score` validation.
2. **Application/service layer** — unit tests against fakes implementing each port (`InMemoryJobRepository`,
   `FakeLLMProvider`, `InMemoryEventBus` that records published events for assertion, `FakeClock`). Most
   business-logic tests live here and run in milliseconds.
3. **Infrastructure** — `SqlAlchemy*Repository` tests against real aiosqlite SQLite (file or in-memory) to
   catch mapping/migration issues. Playwright-based provider tests use recorded HTML/JSON fixtures for CI
   speed, with a separately marked, sparingly run suite against real sites. A shared contract-test suite per
   port, run against both the fake and each real adapter, keeps adapters honest.
4. **Integration** — a thin suite wiring the real composition root (SQLite + in-process bus + fake LLM +
   fake notification channel) driving one full discover → score → apply pipeline through FastAPI's
   `TestClient`.

LLM tests assert schema conformance (valid JSON, 0–100 range, non-empty explanation), not exact values,
since model output isn't deterministic.

## Docker scope

Phase 1 containerizes the FastAPI backend and Ollama as its own service (official image; the backend points
at it via `OLLAMA_BASE_URL` — the cheapest way to prove the "swap the LLM backend without app changes" story
early). SQLite is a file on a mounted volume, not its own container. The frontend can run in Docker too or
locally in dev. Redis/Celery containers, a reverse proxy/TLS layer, and any multi-user auth infrastructure
are explicitly deferred to the point where the scheduler/event-bus seam is actually exercised — consistent
with the zero-paid-services constraint, since none of this needs a cloud bill to run locally.
