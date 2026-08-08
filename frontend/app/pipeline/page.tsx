"use client";

/**
 * Every job CareerOS has acted on, and what happened to it.
 *
 * The lifecycle is shown as a funnel of the states that exist, not the full eleven -- later states have no data
 * until applying and email monitoring are built, and rendering empty stages would read as failure rather than
 * as "not yet". A note says so explicitly instead.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import { api, ApiError, type ApplicationListResponse } from "@/lib/api";
import { Card, EmptyState, ErrorNote, Eyebrow, StatusPill } from "@/components/ui";

/** The order applications actually move through, so the funnel reads top to bottom. */
const LIFECYCLE = [
  "found",
  "interested",
  "saved",
  "resume_generated",
  "applied",
  "interview",
  "assessment",
  "offer",
  "rejected",
] as const;

export default function PipelinePage() {
  const [data, setData] = useState<ApplicationListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .applications()
      .then(setData)
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.message : "Couldn't load the pipeline."),
      );
  }, []);

  if (error) return <ErrorNote message={error} />;

  const counts = data?.counts_by_status ?? {};
  const reached = LIFECYCLE.filter((status) => counts[status]);
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const withMovement = (data?.items ?? []).filter((item) => item.timeline.length > 1);

  return (
    <div className="space-y-5">
      <Card>
        <Eyebrow>{total} tracked applications</Eyebrow>
        {reached.length === 0 ? (
          <EmptyState title="Nothing tracked yet." action="Find some jobs and every one gets a record here." />
        ) : (
          <ol className="space-y-2">
            {reached.map((status) => {
              const count = counts[status];
              return (
                <li key={status} className="grid grid-cols-[9rem_1fr_3rem] items-center gap-3">
                  <StatusPill status={status} />
                  <div className="h-[6px] overflow-hidden rounded-[3px]" style={{ background: "var(--hairline)" }}>
                    <div
                      className="h-full rounded-[3px]"
                      style={{ width: `${(count / total) * 100}%`, background: "var(--score-3)" }}
                    />
                  </div>
                  <span className="tnum text-right text-sm">{count}</span>
                </li>
              );
            })}
          </ol>
        )}
        <p className="mt-4 text-xs" style={{ color: "var(--ink-muted)" }}>
          Later stages appear once applying and recruiter-email monitoring are built. Nothing reaches them yet.
        </p>
      </Card>

      <Card>
        <Eyebrow>Recent movement</Eyebrow>
        {withMovement.length === 0 ? (
          <EmptyState
            title="No application has changed state yet."
            action="A score at or above the threshold promotes one from found to interested."
          />
        ) : (
          <ul className="space-y-3">
            {withMovement.slice(0, 25).map((application) => {
              const latest = application.timeline[application.timeline.length - 1];
              return (
                <li key={application.id} className="py-1" style={{ borderTop: "1px solid var(--hairline)" }}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-2">
                    <Link href={`/jobs/${application.job_id}`} className="text-sm hover:underline">
                      {application.job_title}
                      <span style={{ color: "var(--ink-muted)" }}> · {application.company_name}</span>
                    </Link>
                    <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                      {latest.from_status ? `${latest.from_status.replace(/_/g, " ")} → ` : ""}
                      {latest.to_status.replace(/_/g, " ")}
                      {latest.reason ? ` · ${latest.reason}` : ""}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
