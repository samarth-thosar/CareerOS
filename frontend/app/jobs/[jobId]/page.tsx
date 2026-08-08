"use client";

/**
 * One job in full: the reasoning behind its score, the posting itself, and the action that matters here --
 * tailoring a resume for it.
 *
 * A refused tailoring is treated as a real outcome rather than an error to hide. When the model tries to claim
 * something the achievement bank cannot support, the backend returns 422 and the message explains what was
 * rejected; surfacing that verbatim is the point, because it tells the user what to add to their bank.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { api, ApiError, type JobDetail, type ResumeVersion, type TailorOutcome } from "@/lib/api";
import { ScoreBadge, ScoreStrip } from "@/components/ScoreStrip";
import { Button, Card, EmptyState, ErrorNote, Eyebrow, StatusPill } from "@/components/ui";

export default function JobDetailPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;

  const [job, setJob] = useState<JobDetail | null>(null);
  const [versions, setVersions] = useState<ResumeVersion[]>([]);
  const [outcome, setOutcome] = useState<TailorOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [tailoring, setTailoring] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextJob, nextVersions] = await Promise.all([api.job(jobId), api.resumeVersions(jobId)]);
      setJob(nextJob);
      setVersions(nextVersions.items);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Couldn't load this job.");
    }
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function tailor() {
    setTailoring(true);
    setError(null);
    setRefusal(null);
    setOutcome(null);
    try {
      setOutcome(await api.tailor(jobId));
      await load();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 422) {
        setRefusal(caught.message);
      } else {
        setError(caught instanceof ApiError ? caught.message : "Tailoring didn't finish.");
      }
    } finally {
      setTailoring(false);
    }
  }

  if (error) return <ErrorNote message={error} />;
  if (!job) return <p style={{ color: "var(--ink-muted)" }}>Loading…</p>;

  return (
    <div className="space-y-5">
      <Link href="/" className="text-sm hover:underline" style={{ color: "var(--ink-secondary)" }}>
        ← Shortlist
      </Link>

      <Card>
        <div className="grid gap-5 md:grid-cols-[auto_minmax(0,1fr)]">
          <div>
            <ScoreBadge score={job.score} size="lg" />
            <p className="mt-1 text-[11px] uppercase tracking-[0.12em]" style={{ color: "var(--ink-muted)" }}>
              of 100
            </p>
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight">{job.title}</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--ink-secondary)" }}>
              {job.company_name}
              {job.location ? ` · ${job.location}` : ""} · {job.remote_type} · via {job.source}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-4">
              <StatusPill status={job.status} />
              <a
                href={job.url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-sm hover:underline"
                style={{ color: "var(--accent)" }}
              >
                Original posting ↗
              </a>
            </div>
          </div>
        </div>
      </Card>

      {job.score_detail && (
        <Card>
          <Eyebrow>Why it scored {job.score_detail.value}</Eyebrow>
          <ScoreStrip detail={job.score_detail} showLabels />
          <p className="mt-4 text-sm leading-relaxed" style={{ color: "var(--ink-secondary)" }}>
            {job.score_detail.narrative}
          </p>
          <p className="mt-3 text-[11px]" style={{ color: "var(--ink-muted)" }}>
            {job.score_detail.model_used} · scoring strategy {job.score_detail.strategy_version}
          </p>
        </Card>
      )}

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <Eyebrow>Resume</Eyebrow>
          <Button onClick={tailor} disabled={tailoring}>
            {tailoring ? "Tailoring… (about a minute)" : "Tailor a resume for this job"}
          </Button>
        </div>

        {refusal && (
          <div
            className="mb-4 rounded-md px-4 py-3 text-sm"
            style={{ boxShadow: "inset 0 0 0 1px var(--status-warning)" }}
          >
            <p className="font-medium">Nothing was written — the draft would have claimed too much.</p>
            <p className="mt-1" style={{ color: "var(--ink-secondary)" }}>
              {refusal}
            </p>
            <p className="mt-1 text-xs" style={{ color: "var(--ink-muted)" }}>
              Add it to data/master/achievements.yaml if you can genuinely claim it, then try again.
            </p>
          </div>
        )}

        {outcome && (
          <div
            className="mb-4 rounded-md px-4 py-3 text-sm"
            style={{ boxShadow: "inset 0 0 0 1px var(--ring)" }}
          >
            <p className="font-medium">
              {outcome.pdf_rendered ? "Resume and PDF written." : "Resume written (LaTeX source only)."}
            </p>
            <p className="mt-1 break-all text-xs" style={{ color: "var(--ink-secondary)" }}>
              {outcome.artifact_directory}
            </p>
            {outcome.pdf_note && (
              <p className="mt-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                {outcome.pdf_note}
              </p>
            )}
            {outcome.gap_count > 0 && (
              <p className="mt-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                {outcome.gap_count} gap{outcome.gap_count === 1 ? "" : "s"} flagged for your approval.
              </p>
            )}
          </div>
        )}

        {versions.length === 0 ? (
          <EmptyState
            title="No resume versions for this job yet."
            action="Tailoring writes a new version each time — nothing is ever overwritten."
          />
        ) : (
          <ul className="space-y-2">
            {versions.map((version) => (
              <li
                key={version.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2"
                style={{ borderTop: "1px solid var(--hairline)" }}
              >
                <div className="min-w-0">
                  <p className="text-sm">{version.diff_summary ?? "Tailored version"}</p>
                  <p className="mt-0.5 text-[11px]" style={{ color: "var(--ink-muted)" }}>
                    {new Date(version.created_at).toLocaleString()} · from master {version.master_version_ref}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span style={{ color: version.render_status === "rendered" ? "var(--status-good)" : "var(--ink-muted)" }}>
                    {version.render_status === "rendered" ? "PDF" : "source only"}
                  </span>
                  {version.has_gaps && <span style={{ color: "var(--status-warning)" }}>gaps flagged</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <Eyebrow>Posting</Eyebrow>
        {job.skills.length > 0 && (
          <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
            Detected: {job.skills.join(" · ")}
          </p>
        )}
        <div className="max-h-[32rem] overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed" style={{ color: "var(--ink-secondary)" }}>
          {job.description}
        </div>
      </Card>
    </div>
  );
}
