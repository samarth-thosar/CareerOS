"use client";

/**
 * The approval queue: things a job asked for that the achievement bank could not honestly support.
 *
 * This page is the visible half of the "never fabricate" guarantee. Every entry here is a claim the system
 * declined to make on the user's behalf, and the only way to clear one is for the user to decide it is true and
 * add it to their bank. That makes it a to-do list, so it is framed as one.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import { api, ApiError, type GapFlag } from "@/lib/api";
import { Card, EmptyState, ErrorNote, Eyebrow } from "@/components/ui";

export default function GapsPage() {
  const [gaps, setGaps] = useState<GapFlag[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .gaps()
      .then((response) => setGaps(response.items))
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Couldn't load gaps."));
  }, []);

  if (error) return <ErrorNote message={error} />;

  // The same requirement often comes up across several jobs; grouping turns a list into a priority order.
  const grouped = new Map<string, GapFlag[]>();
  for (const gap of gaps ?? []) {
    const key = gap.missing_skill_or_requirement;
    grouped.set(key, [...(grouped.get(key) ?? []), gap]);
  }
  const ranked = [...grouped.entries()].sort((a, b) => b[1].length - a[1].length);

  return (
    <div className="space-y-5">
      <Card>
        <Eyebrow>{gaps?.length ?? 0} gaps awaiting your decision</Eyebrow>
        <p className="mb-4 max-w-2xl text-sm" style={{ color: "var(--ink-secondary)" }}>
          Each of these was asked for by a job and left off your resume, because nothing in your achievement bank
          supports it. Add the ones you can genuinely claim to{" "}
          <code className="text-xs" style={{ color: "var(--ink)" }}>
            data/master/achievements.yaml
          </code>
          , then tailor again.
        </p>

        {ranked.length === 0 ? (
          <EmptyState
            title="No gaps flagged."
            action="Tailor a resume for a job and anything it asks for that you can't back up shows up here."
          />
        ) : (
          <ul className="space-y-3">
            {ranked.map(([requirement, occurrences]) => (
              <li key={requirement} className="pt-3" style={{ borderTop: "1px solid var(--hairline)" }}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <p className="max-w-2xl text-sm">{requirement}</p>
                  <span className="tnum text-xs" style={{ color: "var(--ink-muted)" }}>
                    {occurrences.length} job{occurrences.length === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3">
                  {occurrences.map((gap) => (
                    <Link
                      key={gap.id}
                      href={`/jobs/${gap.job_id}`}
                      className="text-[11px] hover:underline"
                      style={{ color: "var(--accent)" }}
                    >
                      view job →
                    </Link>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
