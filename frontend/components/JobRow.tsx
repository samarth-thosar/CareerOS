"use client";

import Link from "next/link";

import type { JobSummary } from "@/lib/api";
import { ScoreBadge, ScoreStrip } from "@/components/ScoreStrip";
import { SourceBadge, StatusPill } from "@/components/ui";

function salaryLabel(job: JobSummary): string | null {
  if (job.salary_min === null || job.salary_max === null) return null;
  const format = (amount: number) => `${Math.round(amount / 1000)}k`;
  const currency = job.salary_currency ?? "";
  // Parsed-from-prose figures are marked, because an approximate number presented as exact is worse than none.
  const approximate = job.salary_is_estimated ? "~" : "";
  return `${approximate}${currency} ${format(job.salary_min)}-${format(job.salary_max)}`.trim();
}

export function JobRow({
  job,
  selectable = false,
  selected = false,
  onToggle,
}: {
  job: JobSummary;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: (jobId: string) => void;
}) {
  const salary = salaryLabel(job);

  return (
    <li className="flex items-start gap-2" style={{ borderTop: "1px solid var(--hairline)" }}>
      {selectable && (
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle?.(job.id)}
          aria-label={`Select ${job.title} at ${job.company_name} to apply`}
          className="mt-4 shrink-0"
        />
      )}
      <Link
        href={`/jobs/${job.id}`}
        className="grid flex-1 grid-cols-[3rem_1fr] items-start gap-4 px-1 py-3 transition-colors md:grid-cols-[3rem_minmax(0,1fr)_14rem]"
        style={{ color: "var(--ink)" }}
      >
        <div className="pt-0.5 text-right">
          <ScoreBadge score={job.score} />
        </div>

        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <p className="truncate text-sm font-medium">{job.title}</p>
            <SourceBadge source={job.source} />
          </div>
          <p className="mt-0.5 truncate text-xs" style={{ color: "var(--ink-secondary)" }}>
            {job.company_name}
            {job.location ? ` · ${job.location}` : ""}
            {job.remote_type !== "unknown" ? ` · ${job.remote_type}` : ""}
            {salary ? ` · ${salary}` : ""}
          </p>
          {job.skills.length > 0 && (
            <p className="mt-1 truncate text-[11px]" style={{ color: "var(--ink-muted)" }}>
              {job.skills.slice(0, 8).join(" · ")}
            </p>
          )}
        </div>

        <div className="hidden md:block">
          {job.score_detail ? (
            <ScoreStrip detail={job.score_detail} />
          ) : (
            <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
              queued for scoring
            </p>
          )}
          <div className="mt-2">
            <StatusPill status={job.status} />
          </div>
        </div>
      </Link>
    </li>
  );
}
