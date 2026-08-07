# CareerOS Architecture — Overview

## Vision

CareerOS is a personal AI career operating system, not a job-application bot. It discovers jobs, scores
them against the user's profile, tailors resumes and cover letters, tracks every application through its
lifecycle, and — in later phases — monitors recruiter email and notifies the user over WhatsApp, all behind
a dashboard. The system is designed to keep growing for years, so every module boundary below is chosen to
make future capabilities additive (new job sources, new LLM backends, new notification channels) rather
than requiring changes to existing code.

## Confirmed architectural decisions

| # | Decision | ADR |
|---|---|---|
| 1 | Async-first execution (FastAPI async, async SQLAlchemy/aiosqlite, Playwright async API, AsyncIO scheduler) | [0001](decisions/0001-async-first-execution-model.md) |
| 2 | In-process domain event bus, designed to be swappable for Redis/Celery later | [0002](decisions/0002-in-process-event-bus-with-swappable-backend.md) |
| 3 | Manual composition root for dependency injection — no DI framework | [0003](decisions/0003-manual-composition-root-for-dependency-injection.md) |
| 4 | Layered configuration: YAML for domain tunables, `.env` for secrets, via pydantic-settings | [0004](decisions/0004-layered-yaml-plus-env-configuration.md) |
| 5 | Zero paid services — every adapter defaults to a free/local option | [0005](decisions/0005-zero-paid-services-constraint.md) |

## Layering

Four layers. Dependencies point strictly inward, toward the domain:

```
┌─────────────────────────────────────────────────────────────┐
│ Presentation   (FastAPI routers, WhatsApp inbound webhook)   │
│   depends on ↓                                                │
├─────────────────────────────────────────────────────────────┤
│ Application    (use-case services, ports/interfaces, DTOs)   │
│   depends on ↓                                                │
├─────────────────────────────────────────────────────────────┤
│ Domain         (entities, value objects, domain events,      │
│                 repository ports, pure business rules)       │
└─────────────────────────────────────────────────────────────┘

Infrastructure (SQLAlchemy repos, Ollama client, job-source     ─── implements ports
scrapers, event bus, scheduler adapter, config loader) ────────▶ defined by Application/Domain

Composition Root (bootstrap.py) ──────────────────────────────── the only module that sees
                                                                   all four layers at once
```

**Domain layer** has zero framework imports (no FastAPI, SQLAlchemy, Playwright, pydantic-settings,
APScheduler). It contains entities/aggregates, value objects, domain services encoding business rules with
no I/O, domain events (data-only), and repository *ports* — expressed entirely in domain vocabulary
(`JobRepository.find_by_source(...) -> Job | None`) even though only infrastructure ever implements them.

**Application layer** orchestrates use cases: `DiscoveryService`, `ScoringService`,
`ApplicationTrackerService`, `ResumeManagerService`, `CoverLetterService`, `CompanyIntelligenceService`,
`NotificationService`, `CommandDispatcher`, `MemoryService`. Each depends only on domain types plus the
application-layer ports it needs to reach external systems: `JobSourceProvider`, `LLMProvider`, `EventBus`,
`NotificationChannel`, `EmailProvider`, `ResumeSource`, `SchedulerPort`, `Clock`, `IdGenerator`. This layer
also defines the DTOs that cross into presentation, so the REST contract never leaks raw domain entities.

**Infrastructure layer** holds every concrete adapter: SQLAlchemy repositories, `OllamaProvider`,
per-source job providers (`WellfoundProvider`, later Greenhouse/Lever/Ashby/generic/LinkedIn),
`InProcessEventBus` (later `RedisEventBus`), `APSchedulerAdapter`, Alembic migrations, and the
pydantic-settings loading code itself.

**Presentation layer** keeps FastAPI routers thin: parse request → call an application service → map the
result to a response DTO. The future WhatsApp inbound webhook lives here too, translating a provider
payload into an `InboundCommandReceived` event. FastAPI's `Depends` is used only for request-scoped
plumbing (DB session, resolving already-built services from `app.state`) — never as a substitute for
constructor injection, which keeps dependency injection singular (see ADR-0003).

**Composition root** (`infrastructure/bootstrap.py`) is the only module allowed to import concrete
infrastructure *and* wire it into application services *and* touch the FastAPI app object. It:
1. Loads `Settings` (layered YAML + env).
2. Builds the async engine/sessionmaker.
3. Builds the `EventBus`.
4. Builds each adapter — stateless ones as singletons (`OllamaProvider`, job-source providers), session-scoped
   ones as factories (repositories).
5. Builds each application service with its dependencies passed to `__init__`.
6. Registers the event subscription table explicitly — a flat, greppable list (`service.method ← EventType`),
   not decorator magic.
7. Registers scheduled jobs via `SchedulerPort`.
8. Hooks scheduler start/stop into FastAPI's lifespan.

## Non-goals for this phase

No real job scraping, LLM prompting, resume tailoring, or dashboard UI beyond a single wiring-check page.
No working Celery/Redis (only the `SchedulerPort`/`EventBus` seam). No working Gmail or WhatsApp integration
(ports and DTOs only). No multi-user auth — a single implicit user, `CandidateProfile` is a single row.
These land in later phases per the project roadmap (Phase 4 onward).
