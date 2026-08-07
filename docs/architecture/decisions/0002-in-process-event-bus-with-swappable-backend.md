# 0002 — In-Process Domain Event Bus With a Swappable Backend

## Context

CareerOS's modules (Discovery, Scoring, Application Tracker, Company Intelligence, Resume Manager,
Notifications, Memory) need to react to each other's state changes. A central orchestrator calling every
module's methods in sequence is the simplest option, but the project is explicitly meant to keep growing for
years — every new capability (WhatsApp notifications, email monitoring, memory-driven suggestions) would
otherwise require editing that central orchestrator.

## Decision

Modules communicate through domain events published on an `EventBus` port, not through direct method calls
between services. Phase 1 implements this with an `InProcessEventBus` (in-memory pub/sub, single process).
The `EventBus` protocol is designed so it can later be backed by Redis pub/sub or a real message queue
without changing any publisher or subscriber code — only the composition root's wiring changes.

## Consequences

- Adding a new capability means subscribing to existing events, not modifying an orchestrator. E.g., the
  future WhatsApp notifier subscribes to `ApplicationStatusChanged` and `ResumeGapFlagged`; it never needs
  `ApplicationTrackerService` or `ResumeManagerService` to know it exists.
- Event payloads must stay thin and ID-carrying (not full aggregate snapshots) specifically so the eventual
  Redis swap doesn't require reshaping every event — see the event catalog doc for the granularity rule this
  produced.
- Tracing an end-to-end flow requires following the event chain rather than a single call stack, which is
  why every event carries a `correlation_id` in its envelope, threaded through structured logs.
- The event subscription table is registered explicitly and flatly in the composition root (no decorator-based
  auto-registration), so "what listens to what" stays a single greppable list even as the module count grows.

## Alternatives considered

**Direct orchestration** (a central pipeline service explicitly calling each module in sequence). Easier to
trace step by step in a debugger, and slightly less indirection for a small number of modules. Rejected
because the orchestrator would need to change on every new module addition, working against the project's
explicit years-long growth goal, and because several modules (Memory, Notifications, Company Intelligence)
are naturally reactive observers rather than steps in a linear pipeline.
