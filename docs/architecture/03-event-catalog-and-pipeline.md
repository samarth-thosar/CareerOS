# CareerOS Architecture — Event Catalog and Pipeline

## Granularity rule

One event per meaningful aggregate-state transition — thin and ID-carrying, not full-aggregate snapshots and
not generic `XUpdated` diff events. Subscribers needing more than the headline fields re-query the repository
by id. This keeps payloads small and stable, which matters for the eventual Redis swap (ADR-0002).

Every event carries a common envelope: `event_id`, `event_type`, `occurred_at`, `correlation_id` (see
[04](04-scheduler-config-and-testing.md) for how `correlation_id` is used in logging).

## Event catalog

| Event | Published by | Key fields | Typical subscribers |
|---|---|---|---|
| `JobDiscovered` | `DiscoveryService` | `job_id`, `company_id`, `source`, `url` | `ApplicationTrackerService` (create `Application@Found`), `CompanyIntelligenceService` (upsert open role), `ScoringService` |
| `JobScored` | `ScoringService` | `job_id`, `score_id`, `value`, `scoring_strategy_version` | `ApplicationTrackerService` (maybe `Found → Interested`), `MemoryService`, dashboard read-model |
| `ApplicationStatusChanged` | `ApplicationTrackerService` | `application_id`, `job_id`, `from_status`, `to_status`, `reason`, `actor` | `NotificationService`, `CompanyIntelligenceService`, `MemoryService`, dashboard |
| `ResumeTailoringRequested` | `ApplicationTrackerService` / `CommandDispatcher` | `application_id`, `job_id`, `trigger` | `ResumeManagerService` |
| `ResumeGenerated` | `ResumeManagerService` | `resume_version_id`, `job_id`, `application_id`, `has_gaps` | `ApplicationTrackerService`, `CoverLetterService`, `NotificationService` (if gaps) |
| `ResumeGapFlagged` | `ResumeManagerService` | `gap_flag_id`, `resume_version_id`, `missing_item` | `NotificationService`, dashboard approval queue |
| `CoverLetterGenerated` | `CoverLetterService` | `cover_letter_id`, `job_id`, `resume_version_id` | `ApplicationTrackerService` |
| `ApplicationReadyToApply` | `ApplicationTrackerService` / apply-decision logic | `application_id`, `job_id`, `score` | `NotificationService` (approval ask) or `ApplicationSubmissionService` (if auto-apply gate passes) |
| `InboundCommandReceived` | WhatsApp webhook route | `command_id`, `intent`, `parameters` | `CommandDispatcher` |
| `ApplicationSubmitted` | `ApplicationSubmissionService` | `application_id`, `job_id`, `method`, `confirmation_ref` | `ApplicationTrackerService` (→ `Applied`, sets `applied_at`), `CompanyIntelligenceService`, `NotificationService`, `MemoryService` |
| `RecruiterEmailDetected` (future) | Email module | `email_message_id`, `classification`, `confidence`, linked ids | `CompanyIntelligenceService`, `ApplicationTrackerService`, `NotificationService` |
| `MemoryInsightsUpdated` | `MemoryService` | `insight_type`, `payload` | `ScoringService`, `ResumeManagerService` (as *suggestions* — see approval note below) |

## Primary pipeline (event sequence)

1. Scheduler fires `DiscoveryService.run_cycle()` per enabled provider (staggered). New postings are
   mapped, de-duplicated against `JobRepository.find_by_source(...)`, and persisted inside a unit of work;
   on commit, `JobDiscovered` is published.
2. `JobDiscovered` fans out: `ApplicationTrackerService` creates `Application(status=Found)`;
   `CompanyIntelligenceService` upserts the `Company` profile; `ScoringService` enqueues a scoring task onto
   a bounded worker queue (deliberately not unbounded concurrent LLM calls — a local Ollama instance
   serializes generation anyway, so it's better to own that queue explicitly).
3. `ScoringService` builds a prompt from `Job` + `CandidateProfile` + a versioned prompt template, calls
   `LLMProvider.complete()` with a JSON response schema, persists `Score`, publishes `JobScored`.
4. `ApplicationTrackerService` reacts to `JobScored`: attaches the score; if `value >= auto_interested_threshold`,
   transitions `Found → Interested` and publishes `ApplicationStatusChanged`. `MemoryService` records
   `(job_id, score, strategy_version)` for later outcome correlation.
5. On reaching `Interested` (auto or via a user command), `ResumeTailoringRequested` fires.
   `ResumeManagerService` fetches the last-synced master resume, tailors via LLM, emits `ResumeGapFlag`s for
   anything it can't honestly support rather than inventing content, renders a PDF, persists a new
   `ResumeVersion`, publishes `ResumeGenerated`. `CoverLetterService` reacts and produces a `CoverLetter`.
   `ApplicationTrackerService` attaches both and moves to `ResumeGenerated`.
6. Decision to submit: if `auto_apply_enabled` and the score clears the apply threshold and no gap flags are
   pending, `ApplicationReadyToApply` routes straight to `ApplicationSubmissionService`. Otherwise
   `NotificationService` sends a WhatsApp approval ask; only `InboundCommandReceived(ApplyApproved)` triggers
   submission.
7. `ApplicationSubmissionService` re-checks `applied_at is None` (race guard), performs the submission (or,
   for sources without `supports_auto_submit`, exposes a "here's the apply URL, confirm once you've applied"
   path), and on success publishes `ApplicationSubmitted`. `ApplicationTrackerService` transitions to
   `Applied` and locks `applied_at`.
8. `NotificationService` sends an immediate, non-batched "Applied to X" message; `CompanyIntelligenceService`
   and `MemoryService` record the outcome.
9. *(Future)* Email module detects recruiter activity → `RecruiterEmailDetected` → `ApplicationTrackerService`
   maps the classification to a status transition (`Interview`/`Assessment`/`RecruiterContact`/`Offer`/
   `Rejected`) → same downstream fan-out.
10. Nightly, `MemoryService` recomputes read-model aggregates (response rate by resume version / technology /
    company) directly from repositories. This is the one place business logic is deliberately bypassed —
    pure reporting has no business logic, and a light CQRS split (write side through aggregates + events,
    read side through direct repository/read-model queries) keeps the dashboard fast without forcing every
    `GET` through domain machinery.

## Notification batching policy

`JobDiscovered`/`JobScored` are batched into a periodic digest ("Found 5 new jobs, 3 scored above 80")
rather than pinging per job. High-urgency transitions — `Interview`, `Offer`, assessment-deadline warnings —
bypass batching and send immediately. This is an internal policy of `NotificationService`, not a separate
port.

## Memory feedback — approval gate

`MemoryInsightsUpdated` never silently mutates live `ScoringWeights`. `MemoryService` writes suggested
weight changes to a review queue that surfaces on the dashboard; a human approves before a suggestion
becomes active configuration. This mirrors the same "never fabricate, ask approval for consequential
changes" principle applied to the Resume Manager, and is revisited when Phase 12 (Memory) is built.
