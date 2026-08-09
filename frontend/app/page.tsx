"use client";

/**
 * The shortlist -- the page the product exists for.
 *
 * The hero is the top match and the reasoning behind it, rather than a row of KPI tiles: the decision the user
 * came to make is "is anything here worth my evening", and a count of 224 does not answer that. Numbers that
 * do matter (how much of the backlog is scored, how many clear the threshold) sit in a thin strip above.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  api,
  ApiError,
  applyApi,
  type JobListResponse,
  type Overview,
  type SubmitResponse,
} from "@/lib/api";
import { JobRow } from "@/components/JobRow";
import { ScoreBadge, ScoreStrip } from "@/components/ScoreStrip";
import { Button, Card, EmptyState, ErrorNote, Eyebrow, StatusPill } from "@/components/ui";

const PAGE_SIZE = 50;

interface Filters {
  search: string;
  remoteType: string;
  technology: string;
  minScore: string;
  onlyScored: boolean;
}

const EMPTY_FILTERS: Filters = { search: "", remoteType: "", technology: "", minScore: "", onlyScored: true };

export default function ShortlistPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [jobs, setJobs] = useState<JobListResponse | null>(null);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // Selection is explicit and never inferred: CareerOS lists, the user picks, CareerOS applies.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submission, setSubmission] = useState<SubmitResponse | null>(null);

  const query = useMemo(
    () => ({
      ranked: true,
      limit: PAGE_SIZE,
      search: filters.search.trim() || undefined,
      remoteType: filters.remoteType || undefined,
      technology: filters.technology.trim() || undefined,
      minScore: filters.minScore ? Number(filters.minScore) : filters.onlyScored ? 1 : undefined,
    }),
    [filters],
  );

  const load = useCallback(async () => {
    try {
      const [nextOverview, nextJobs] = await Promise.all([api.overview(), api.jobs(query)]);
      setOverview(nextOverview);
      setJobs(nextJobs);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong loading the shortlist.");
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    setError(null);
    try {
      await action();
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : `${label} didn't finish.`);
    } finally {
      setBusy(null);
    }
  }

  function toggle(jobId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(jobId) ? next.delete(jobId) : next.add(jobId);
      return next;
    });
  }

  async function applyToSelected() {
    setBusy("Applying");
    setError(null);
    setSubmission(null);
    try {
      setSubmission(await applyApi.submit([...selected]));
      setSelected(new Set());
      await load();
    } catch (caught) {
      // 409 means required profile answers are still blank -- an actionable message, not a failure to hide.
      setError(caught instanceof ApiError ? caught.message : "Couldn't submit those applications.");
    } finally {
      setBusy(null);
    }
  }

  const [top, ...rest] = jobs?.items ?? [];

  return (
    <div className="space-y-6">
      {error && <ErrorNote message={error} />}

      <StatusStrip overview={overview} busy={busy} onDiscover={() => run("Finding jobs", api.discover)} onScore={() => run("Scoring", () => api.scoreBatch(10))} />

      {submission && <SubmissionReport report={submission} />}

      {selected.size > 0 && (
        <div
          className="sticky top-14 z-10 flex flex-wrap items-center gap-3 rounded-lg px-4 py-3"
          style={{ background: "var(--surface)", boxShadow: "inset 0 0 0 1px var(--accent)" }}
        >
          <span className="text-sm">
            <span className="tnum font-semibold">{selected.size}</span> selected
          </span>
          <Button onClick={applyToSelected} disabled={busy !== null}>
            {busy === "Applying" ? "Applying…" : "Apply to selected"}
          </Button>
          <Button variant="quiet" onClick={() => setSelected(new Set())} disabled={busy !== null}>
            Clear
          </Button>
        </div>
      )}

      {top?.score_detail && <TopMatch job={top} />}

      <Card>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <Eyebrow>
            {jobs ? `${jobs.matched} of ${jobs.total} jobs` : "Shortlist"}
          </Eyebrow>
          <FilterRow filters={filters} onChange={setFilters} />
        </div>

        {jobs && jobs.items.length === 0 ? (
          <EmptyState
            title="No jobs match these filters."
            action={
              overview && overview.jobs_scored === 0
                ? "Nothing is scored yet — run Score next 10 to start ranking."
                : "Try clearing the filters, or widen the minimum score."
            }
          />
        ) : (
          <ul>
            {(top ? [top, ...rest] : []).map((job) => (
              <JobRow
                key={job.id}
                job={job}
                selectable
                selected={selected.has(job.id)}
                onToggle={toggle}
              />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/** Thin strip of the few counts that change what you do next, plus the two actions that change them. */
function StatusStrip({
  overview,
  busy,
  onDiscover,
  onScore,
}: {
  overview: Overview | null;
  busy: string | null;
  onDiscover: () => void;
  onScore: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <dl className="flex flex-wrap items-baseline gap-x-6 gap-y-2 text-sm">
        <Stat label="found" value={overview?.jobs_total} />
        <Stat label="scored" value={overview?.jobs_scored} />
        <Stat label="queued" value={overview?.jobs_unscored} />
        <Stat
          label={overview ? `at or above ${overview.shortlist_threshold}` : "shortlisted"}
          value={overview?.shortlist_size}
        />
      </dl>
      <div className="ml-auto flex gap-2">
        <Button variant="quiet" onClick={onDiscover} disabled={busy !== null}>
          {busy === "Finding jobs" ? "Finding…" : "Find new jobs"}
        </Button>
        <Button onClick={onScore} disabled={busy !== null}>
          {busy === "Scoring" ? "Scoring…" : "Score next 10"}
        </Button>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dd className="tnum text-lg font-semibold tracking-tight">{value ?? "—"}</dd>
      <dt className="text-xs" style={{ color: "var(--ink-muted)" }}>
        {label}
      </dt>
    </div>
  );
}

/** The hero: the single best match, with the reasoning that put it there. */
function TopMatch({ job }: { job: NonNullable<JobListResponse["items"][number]> }) {
  return (
    <Card className="!p-6">
      <Eyebrow>Best match right now</Eyebrow>
      <div className="grid gap-5 md:grid-cols-[auto_minmax(0,1fr)]">
        <div className="flex items-start gap-4 md:block">
          <ScoreBadge score={job.score} size="lg" />
          <p className="mt-1 text-[11px] uppercase tracking-[0.12em]" style={{ color: "var(--ink-muted)" }}>
            of 100
          </p>
        </div>

        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">
            <Link href={`/jobs/${job.id}`} className="hover:underline">
              {job.title}
            </Link>
          </h1>
          <p className="mt-1 text-sm" style={{ color: "var(--ink-secondary)" }}>
            {job.company_name}
            {job.location ? ` · ${job.location}` : ""} · via {job.source}
          </p>

          {job.score_detail && (
            <>
              <div className="mt-4">
                <ScoreStrip detail={job.score_detail} showLabels />
              </div>
              <p className="mt-4 max-w-2xl text-sm leading-relaxed" style={{ color: "var(--ink-secondary)" }}>
                {job.score_detail.narrative}
              </p>
            </>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <StatusPill status={job.status} />
            <Link href={`/jobs/${job.id}`} className="text-sm font-medium hover:underline" style={{ color: "var(--accent)" }}>
              Open and tailor resume →
            </Link>
          </div>
        </div>
      </div>
    </Card>
  );
}

/** Filters sit in one row directly above the list they affect. */
function FilterRow({ filters, onChange }: { filters: Filters; onChange: (next: Filters) => void }) {
  const field = {
    background: "var(--surface-raised)",
    color: "var(--ink)",
    boxShadow: "inset 0 0 0 1px var(--ring)",
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        value={filters.search}
        onChange={(event) => onChange({ ...filters, search: event.target.value })}
        placeholder="Title or company"
        aria-label="Search by title or company"
        className="w-44 rounded-md px-2.5 py-1.5 text-sm"
        style={field}
      />
      <input
        type="text"
        value={filters.technology}
        onChange={(event) => onChange({ ...filters, technology: event.target.value })}
        placeholder="Technology"
        aria-label="Filter by technology"
        className="w-32 rounded-md px-2.5 py-1.5 text-sm"
        style={field}
      />
      <select
        value={filters.remoteType}
        onChange={(event) => onChange({ ...filters, remoteType: event.target.value })}
        aria-label="Filter by work arrangement"
        className="rounded-md px-2.5 py-1.5 text-sm"
        style={field}
      >
        <option value="">Anywhere</option>
        <option value="remote">Remote</option>
        <option value="hybrid">Hybrid</option>
        <option value="onsite">Onsite</option>
      </select>
      <select
        value={filters.minScore}
        onChange={(event) => onChange({ ...filters, minScore: event.target.value })}
        aria-label="Minimum score"
        className="rounded-md px-2.5 py-1.5 text-sm"
        style={field}
      >
        <option value="">Any score</option>
        <option value="70">70+</option>
        <option value="60">60+</option>
        <option value="50">50+</option>
      </select>
      <label className="flex items-center gap-1.5 text-xs" style={{ color: "var(--ink-secondary)" }}>
        <input
          type="checkbox"
          checked={filters.onlyScored}
          onChange={(event) => onChange({ ...filters, onlyScored: event.target.checked })}
        />
        Scored only
      </label>
    </div>
  );
}


/**
 * What actually happened to each selected job.
 *
 * Skips are reported as prominently as successes, with the reason: "no tailored resume yet" and
 * "this board's forms are not automatable" need different actions from the user, and collapsing them into a
 * single failure count would hide which.
 */
function SubmissionReport({ report }: { report: SubmitResponse }) {
  return (
    <Card>
      <Eyebrow>
        {report.counts.submitted} submitted · {report.counts.skipped} skipped
      </Eyebrow>
      {report.skipped.length > 0 && (
        <ul className="space-y-2">
          {report.skipped.map((item) => (
            <li key={item.job_id} className="text-sm" style={{ color: "var(--ink-secondary)" }}>
              <span style={{ color: "var(--status-warning)" }}>•</span> {item.reason}
              {item.manual_url && (
                <>
                  {" — "}
                  <a
                    href={item.manual_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="hover:underline"
                    style={{ color: "var(--accent)" }}
                  >
                    open the form ↗
                  </a>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
