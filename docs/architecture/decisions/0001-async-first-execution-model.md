# 0001 — Async-First Execution Model

## Context

CareerOS's core workloads — browser automation (Playwright), LLM inference (Ollama), and future email/API
polling — are I/O-bound. The backend is FastAPI, which is async-native. A choice was needed between building
the whole backend around `asyncio` (async SQLAlchemy, Playwright's async API, an async scheduler) versus a
simpler synchronous core with blocking calls pushed to a thread pool.

## Decision

Adopt an async-first execution model throughout the backend:
- FastAPI async endpoints.
- SQLAlchemy's async engine with the `aiosqlite` driver.
- Playwright's async API for all browser automation.
- An `asyncio`-based scheduler (APScheduler's `AsyncIOScheduler`) for periodic work.

## Consequences

- I/O-bound work (scraping, LLM calls, future API polling) can run concurrently without spinning up threads
  or processes, and composes naturally with FastAPI's own async request handling.
- The eventual move to Celery/Redis (deferred, see [0002](0002-in-process-event-bus-with-swappable-backend.md))
  is a smaller step from an async codebase than from a sync one, since Celery workers can host the same
  async service code inside their own event loop.
- Care is required: because the scheduler shares FastAPI's event loop, every adapter must genuinely use
  async I/O (`await`) rather than blocking calls, or a slow scrape will stall the whole app. This is called
  out explicitly in the scheduler design doc as an implementation-phase risk to watch.
- Testing requires `pytest-asyncio`, and domain-layer tests (which have no I/O) are kept deliberately
  synchronous so the majority of fast unit tests don't pay any async overhead.

## Alternatives considered

**Sync-first with a thread pool for blocking calls.** Simpler mental model, less async ceremony throughout
the codebase. Rejected because Playwright, an async-native driver stack, and a future Celery migration all
favor asyncio, and offloading to thread pools would need to happen at nearly every I/O boundary anyway —
better to build the abstraction in from the start than retrofit it.
