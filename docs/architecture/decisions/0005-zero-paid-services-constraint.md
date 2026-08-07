# 0005 — Zero Paid Services Constraint

## Context

CareerOS is a personal project intended to run indefinitely at no ongoing monetary cost. Several natural
implementation choices carry a bill: cloud-hosted LLM APIs, cloud hosting/compute, paid job-board APIs, and
WhatsApp messaging providers (e.g. Twilio charges per message; even Meta's own Cloud API has free-tier
limits on messaging windows).

## Decision

Every adapter defaults to a free or local option, and no paid tier is ever adopted without the user's
explicit sign-off first:

- **LLM** — Ollama, running locally (Qwen3 8B by default), never a paid hosted model API.
- **Hosting** — Docker Compose on the user's own machine; no cloud compute bill.
- **Persistence** — SQLite, a local file; no managed database service.
- **Job discovery** — free scraping (Playwright) or free public APIs (Greenhouse, Lever, Ashby); no paid
  job-board API tiers.
- **Email** — the Gmail API's free usage quota.
- **WhatsApp** — deliberately left undecided in this phase. `NotificationChannel` is defined as a port only;
  no adapter is built yet. When Phase 11 (WhatsApp Agent) starts, the choice between Meta's official Cloud
  API (free tier, but bounded by 24-hour messaging-window rules for user-initiated conversations) and a
  self-hosted unofficial bridge (free, but against WhatsApp's terms of service and carries account-ban risk)
  is presented to the user explicitly, with costs and risks named, before either is implemented.

## Consequences

- Every phase-1 adapter choice in [02-ports-and-interfaces.md](../02-ports-and-interfaces.md) is free by
  construction — there is nothing to audit for hidden cost in what's built so far.
- The WhatsApp module stays interface-only until its cost/ToS tradeoff is decided with the user, which is
  consistent with treating consequential, judgment-requiring decisions as things the user signs off on
  rather than something automated silently.
- If a future phase surfaces a case where the free option is meaningfully worse (e.g. free-tier rate limits
  make discovery too slow), that tradeoff gets raised explicitly rather than silently upgraded to a paid
  tier.

## Alternatives considered

**Twilio for WhatsApp messaging.** Reliable, well-documented, but billed per message — rejected outright by
the user's stated preference for zero ongoing cost. **Paid job-board APIs** (e.g. some LinkedIn or Indeed
partner tiers). Rejected for the same reason; free public APIs and Playwright-based scraping cover the
sources currently in scope (Wellfound, Greenhouse, Lever, Ashby, generic career pages, LinkedIn search-only).
