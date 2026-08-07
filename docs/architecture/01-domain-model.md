# CareerOS Architecture — Domain Model

All entities below live in `backend/src/careeros/domain/` with zero framework imports. Aggregates own their
invariants; value objects are immutable.

## Job (aggregate root — Discovery)

Append-only discovery record.

| Field | Notes |
|---|---|
| `id` | |
| `source` | enum: `wellfound`, `greenhouse`, `lever`, `ashby`, `generic`, `linkedin` |
| `source_job_id` | provider's native id for the posting |
| `company_id` | |
| `title`, `url`, `description` | |
| `location` | value object: `city`, `country`, `remote_type` |
| `salary_range` | value object: `min`, `max`, `currency`, `period`, `is_estimated` |
| `skills` | `list[str]` |
| `posting_date`, `discovered_at` | |
| `raw_payload` | original provider payload, kept for audit |

**Invariant:** uniqueness of `(source, source_job_id)` — rediscovering a posting is a no-op, not a new `Job`.
Raw provider payloads never cross into `Job`'s public fields directly; a per-provider mapper (anti-corruption
layer) in infrastructure does the translation.

## Company (aggregate root — Company Intelligence)

`id`, `name`, `website`, `careers_page_url`, `linkedin_url`, `industry`, `funding_stage`, `size_estimate`,
`tech_stack: list[str]` (accumulated over time), `engineering_blog_url`, `notes: list[TimestampedNote]`
(append-only), `recruiter_contacts: list[RecruiterContact]`, `version` (optimistic lock — Email, Discovery,
and Application modules all enrich this concurrently).

`open_roles` and `response_history` are **not** stored redundantly on the aggregate — they are read-model
queries over `Job`/`Application`, to avoid two sources of truth.

### RecruiterContact

`id`, `company_id`, `name`, `email`, `linkedin`, `role`, `first_contacted_at`, `last_contacted_at`, `channel`.

## Score (immutable, append-only — Scoring)

`id`, `job_id`, `value` (0–100), `explanation` (structured breakdown: `resume_match`, `skill_area_fit`,
`career_progression_fit`, `remote_fit`, `salary_fit`, `company_quality`, plus narrative text),
`scoring_strategy_version`, `model_used`, `created_at`.

Re-scoring never mutates a `Score` — it inserts a new row; "current score" is the latest by `created_at`.
This is deliberate: Memory needs score history to correlate scoring-strategy versions with outcomes.

## Application (aggregate root — Application Tracker, the central lifecycle object)

`id`, `job_id` (**unique** — structural 1:1 with `Job`), `status`, `status_history: list[ApplicationStatusEvent]`
(append-only), `current_resume_version_id`, `current_cover_letter_id`, `applied_at` (nullable), `version`
(optimistic lock).

State machine:

```
Found → Interested → Saved → ResumeGenerated → Applied → {Interview, Assessment, RecruiterContact}
                                                              ↘ Rejected / Offer → Archived
```

`Rejected` and `Archived` are reachable from most states, not only the terminal ones shown above.

### "Never apply twice" — defense in depth

1. **Domain (primary).** `Application.apply()` checks `applied_at is not None` and raises
   `AlreadyAppliedError` unconditionally — not just on "current status" — because status can move
   `Applied → Interview → Rejected` and must still never re-fire apply.
2. **Database.** A unique constraint on `Application.job_id` means there is structurally only one lifecycle
   per job; a second `Application` row cannot be created to route around the domain check.
3. **Race guard.** `ApplicationSubmissionService` re-fetches and re-checks `applied_at` immediately before
   the actual submission, and saves with optimistic concurrency (`version` column) so two concurrently
   triggered "apply" commands cannot both win.

## ResumeVersion (aggregate root — Resume Manager)

`id`, `source_master_version_ref` (hash/id of the Overleaf snapshot it derives from), `job_id` (nullable —
null for the synced master baseline), `content`, `diff_summary` (human-readable), `render_status`
(`Draft → Rendered`, one-way), `pdf_path`, `created_at`, `has_gaps`.

**Immutability.** The entity exposes no update methods beyond a single one-shot `mark_rendered(pdf_path)`
transition; calling it twice raises. The repository additionally refuses any `UPDATE` once
`render_status == Rendered`. Any further tailoring is always a brand-new row referencing the same `job_id`.

### ResumeGapFlag

"Never fabricate" is not a pure entity invariant — it is enforced at the service/prompting level, but the
model gives it a home. `id`, `resume_version_id`, `job_id`, `missing_skill_or_requirement`,
`suggested_language`, `status` (`PendingApproval`/`Approved`/`Rejected`). When tailoring discovers the job
needs evidence the master resume doesn't support, the service emits a gap flag instead of inventing content,
and the `ResumeVersion` is marked `has_gaps=true`. The user resolves gaps explicitly.

## CoverLetter (aggregate root)

`id`, `job_id`, `resume_version_id`, `content`, `created_at` — same immutability treatment as `ResumeVersion`.

## EmailMessage (domain shape now, no adapter yet)

`id`, `gmail_message_id`, `thread_id`, `from_address`, `subject`, `received_at`, `classification`
(`RecruiterOutreach`/`InterviewInvite`/`AssessmentInvite`/`OfferLetter`/`Rejection`/`Other`), `confidence`,
`linked_company_id`, `linked_application_id`, `draft_reply_id`, `requires_approval`, `sent_at` (stays `null`
until an explicit approval gate passes — this field's existence is *how* "never auto-send" is enforced).

## NotificationMessage / InboundCommand

Outbound: `id`, `channel`, `template_id`, `payload`, `urgency`, `delivery_status`.
Inbound: `id`, `channel`, `raw_text`, `parsed_intent` (`ApplyApproved`/`ShowInterviews`/`ShowSummary`/
`PauseApplications`/`ResumeApplications`/`GenerateDailyReport`/`Unknown`), `parameters`.

## CandidateProfile (aggregate, single row)

`master_resume_ref`, skills inventory, preferences (remote preference, salary floor, target skill areas:
AI/backend/frontend/MERN/React/Flutter/Python), do-not-apply list, approval-gate toggles.

This is deliberately domain state in the database, distinct from `config/*.yaml`: config holds
deployment-time tunables (scoring *weights*, which providers are enabled, LLM model choice), while
`CandidateProfile` holds business state that the app's own event-driven logic evolves over time and must
audit. Conflating the two would make Memory's feedback loop awkward to reason about.
