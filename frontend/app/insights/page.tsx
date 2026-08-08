"use client";

/**
 * Distributions behind the shortlist: how scores spread, what the market is asking for, who is hiring most.
 *
 * Only metrics the data can currently answer. Interview rate, response rate and offers are in the product
 * vision but no application has reached those states, so they are named as pending rather than rendered as
 * zeros -- a zero implies failure, "not yet" is the truth.
 */

import { useEffect, useState } from "react";

import { api, ApiError, type Breakdowns, type Overview } from "@/lib/api";
import { BarList, Card, ErrorNote, Eyebrow } from "@/components/ui";

export default function InsightsPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [breakdowns, setBreakdowns] = useState<Breakdowns | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.overview(), api.breakdowns()])
      .then(([nextOverview, nextBreakdowns]) => {
        setOverview(nextOverview);
        setBreakdowns(nextBreakdowns);
      })
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.message : "Couldn't load insights."),
      );
  }, []);

  if (error) return <ErrorNote message={error} />;

  return (
    <div className="space-y-5">
      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <Eyebrow>Score distribution</Eyebrow>
          {breakdowns && <ScoreHistogram buckets={breakdowns.score_distribution} threshold={overview?.shortlist_threshold ?? 70} />}
          <p className="mt-3 text-xs" style={{ color: "var(--ink-muted)" }}>
            {overview?.jobs_scored ?? 0} scored · median {overview?.median_score ?? "—"} · best{" "}
            {overview?.top_score ?? "—"}
          </p>
        </Card>

        <Card>
          <Eyebrow>Most requested technologies</Eyebrow>
          <BarList items={breakdowns?.top_technologies ?? []} emptyLabel="No technologies detected yet." />
        </Card>

        <Card>
          <Eyebrow>Companies hiring most</Eyebrow>
          <BarList items={breakdowns?.top_companies ?? []} emptyLabel="No companies yet." />
        </Card>

        <Card>
          <Eyebrow>Work arrangement</Eyebrow>
          <BarList items={breakdowns?.remote_split ?? []} emptyLabel="No jobs yet." />
        </Card>
      </div>

      <Card>
        <Eyebrow>Not measurable yet</Eyebrow>
        <p className="text-sm" style={{ color: "var(--ink-secondary)" }}>
          Interview rate, response rate and offers need applications that have been sent and replied to. Those
          arrive with the applying and recruiter-email phases; until then there is genuinely nothing to plot.
        </p>
      </Card>
    </div>
  );
}

/**
 * A histogram: one bar per 10-point band, x-axis fixed 0–100 so the shape is comparable between refreshes.
 * Bands at or above the shortlist threshold are darker, because that is the only cut in this chart that
 * changes a decision.
 */
function ScoreHistogram({
  buckets,
  threshold,
}: {
  buckets: { floor: number; count: number }[];
  threshold: number;
}) {
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1);
  const scored = buckets.reduce((sum, bucket) => sum + bucket.count, 0);

  if (scored === 0) {
    return (
      <p className="py-8 text-center text-sm" style={{ color: "var(--ink-secondary)" }}>
        Nothing scored yet.
      </p>
    );
  }

  return (
    <figure>
      <div className="flex h-32 items-end gap-[2px]" role="img" aria-label="Distribution of job scores by ten-point band">
        {buckets.map((bucket) => {
          const shortlisted = bucket.floor >= threshold;
          return (
            <div key={bucket.floor} className="flex flex-1 flex-col items-center justify-end gap-1">
              {bucket.count > 0 && (
                <span className="tnum text-[10px]" style={{ color: "var(--ink-muted)" }}>
                  {bucket.count}
                </span>
              )}
              <div
                className="w-full rounded-t-[3px]"
                style={{
                  height: `${(bucket.count / max) * 100}%`,
                  minHeight: bucket.count > 0 ? 3 : 0,
                  background: shortlisted ? "var(--score-5)" : "var(--score-1)",
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex gap-[2px]" style={{ borderTop: "1px solid var(--baseline)" }}>
        {buckets.map((bucket) => (
          <span key={bucket.floor} className="tnum flex-1 pt-1 text-center text-[10px]" style={{ color: "var(--ink-muted)" }}>
            {bucket.floor}
          </span>
        ))}
      </div>
      <figcaption className="mt-2 text-xs" style={{ color: "var(--ink-muted)" }}>
        Darker bands are at or above your shortlist threshold of {threshold}.
      </figcaption>
    </figure>
  );
}
