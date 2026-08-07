# CareerOS Architecture — Ports and Interfaces

Ports are `typing.Protocol` classes. Application-layer services depend only on these, never on concrete
adapters — concrete adapters are wired in by the composition root (`infrastructure/bootstrap.py`). Every
phase-1 adapter is free/local by construction (see [ADR-0005](decisions/0005-zero-paid-services-constraint.md)).

| Port | Owner layer | Minimal shape | Phase-1 adapter | Later adapters |
|---|---|---|---|---|
| `JobSourceProvider` | application | `async search(criteria) -> AsyncIterator[RawJobPosting]`; `name: str`; `supports_auto_submit: bool` | `WellfoundProvider` (Playwright, free) | Greenhouse/Lever/Ashby (free public APIs), generic career page (Playwright + LLM extraction fallback), LinkedIn (search-only) |
| `LLMProvider` | application | `async complete(prompt: PromptSpec, response_schema=None) -> LLMResponse` | `OllamaProvider` (Qwen3 8B, local/free) | Any future model backend — `PromptSpec` stays model-agnostic; the adapter owns chat-template translation |
| `EventBus` | application | `async publish(event: DomainEvent)`; `subscribe(EventType, handler)` | `InProcessEventBus` | `RedisEventBus` / Celery-task-dispatch bus |
| `NotificationChannel` | application | `async send(message: NotificationMessage) -> DeliveryResult` | — (interface only this phase) | `WhatsAppChannel` — adapter choice (Meta Cloud API free tier vs. self-hosted bridge) decided explicitly at Phase 11 |
| `EmailProvider` | application | `async fetch_new_messages(since) -> list[RawEmailMessage]`; `async create_draft_reply(...)`; `async send_draft(...)` (only ever called post-approval) | — (interface only this phase) | `GmailProvider` (free API quota) |
| `ResumeSource` | application | `async fetch_master() -> MasterResumeSnapshot` | — (interface only this phase) | `OverleafSource` |
| Repository per aggregate | domain | `get_by_id`, `add`, `save` (optimistic-locked) + aggregate-specific queries (e.g. `JobRepository.find_by_source(...)`, `ApplicationRepository.has_ever_applied(job_id)`) | `SqlAlchemy*Repository` (SQLite, free) | — |
| `SchedulerPort` | application | `schedule_interval(job_id, coro_factory, seconds)`; `schedule_cron(...)`; `remove(job_id)` | `APSchedulerAdapter` (AsyncIOScheduler, SQLAlchemy jobstore) | Celery Beat adapter |
| `Clock`, `IdGenerator` | application | `now()`, `new_id()` | `SystemClock`, `UuidGenerator` | — kept as ports purely for deterministic testing |

## Design notes

- **Capability flag.** `JobSourceProvider.supports_auto_submit` lets `ApplicationSubmissionService` fall
  back to a "here's the apply URL, confirm once you've applied manually" flow for sources that can't be
  automated, without special-casing providers by name anywhere else in the codebase.
- **Inbound WhatsApp commands** are deliberately *not* modeled as a `receive()` method on
  `NotificationChannel` — a webhook-driven push model fits messaging APIs better. The inbound path is a thin
  FastAPI route that publishes `InboundCommandReceived` directly onto the event bus.
- **Repository ports live in the domain layer** even though only infrastructure implements them, because
  their method signatures are expressed entirely in domain vocabulary. Everything else in the table above is
  an application-layer port, since it exists to orchestrate an external system for a use case rather than to
  express an entity invariant.
- **`PromptSpec` stays model-agnostic.** No prompt template or chat-formatting logic tied to Qwen3 (or any
  other model) lives outside the concrete `LLMProvider` adapter — this is what "the LLM must be completely
  configurable, never hardcode model-specific logic" means structurally.
