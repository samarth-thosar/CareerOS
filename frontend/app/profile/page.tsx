"use client";

/**
 * Where the candidate fills in everything CareerOS refuses to guess.
 *
 * Two design points:
 *
 * - **Outstanding fields lead.** The page opens with what is still missing, because that list is the only thing
 *   standing between the system and being able to apply. Everything else is reference.
 * - **Unanswered is visually distinct from answered-blank.** A field still holding the backend's TODO sentinel is
 *   marked, so "I haven't got to this" never gets confused with "I chose to leave this empty" -- which matters
 *   because the submission guard treats them differently.
 *
 * Saves write straight back to the YAML files on disk, so editing here and editing the file by hand are the same
 * action on the same source of truth.
 */

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  isUnanswered,
  profileApi,
  type ApplicationAnswers,
  type ProfileResponse,
} from "@/lib/api";
import { Button, Card, ErrorNote, Eyebrow } from "@/components/ui";

/** Grouped the way an application form is, so filling this in feels like filling one form once. */
const SECTIONS: { title: string; note?: string; fields: (keyof ApplicationAnswers)[] }[] = [
  {
    title: "Identity",
    fields: ["full_name", "email", "phone", "current_location", "linkedin_url", "github_url", "portfolio_url"],
  },
  {
    title: "Availability",
    note: "Notice period and start date are asked by almost every form.",
    fields: ["notice_period_days", "earliest_start_date", "willing_to_relocate", "preferred_work_arrangement"],
  },
  {
    title: "Compensation",
    note: "Annual. Leave current CTC blank to decline disclosing it — blank is a valid answer.",
    fields: ["salary_currency", "current_ctc", "expected_ctc"],
  },
  {
    title: "Background",
    note: "Experience years moves every job score, so it's worth getting right.",
    fields: ["total_experience_years", "highest_qualification"],
  },
  {
    title: "Cover letter angle",
    note: "Raw material for the 'why this company' paragraph. Yours, so the letter isn't the model's invention.",
    fields: ["why_this_company_template", "additional_information"],
  },
  {
    title: "Optional demographics",
    note: "Every form makes these optional. Blank means prefer not to say.",
    fields: ["gender", "ethnicity", "disability_status", "veteran_status"],
  },
];

const LABELS: Partial<Record<keyof ApplicationAnswers, string>> = {
  full_name: "Full name",
  email: "Email",
  phone: "Phone",
  current_location: "Current location",
  linkedin_url: "LinkedIn",
  github_url: "GitHub",
  portfolio_url: "Portfolio (optional)",
  notice_period_days: "Notice period (days)",
  earliest_start_date: "Earliest start date",
  willing_to_relocate: "Willing to relocate",
  preferred_work_arrangement: "Preferred arrangement",
  salary_currency: "Currency",
  current_ctc: "Current CTC (optional)",
  expected_ctc: "Expected CTC",
  total_experience_years: "Total experience (years)",
  highest_qualification: "Highest qualification",
  why_this_company_template: "What you want out of a role",
  additional_information: "Anything else (optional)",
  gender: "Gender",
  ethnicity: "Ethnicity",
  disability_status: "Disability status",
  veteran_status: "Veteran status",
};

const LONG_FIELDS = new Set<keyof ApplicationAnswers>([
  "why_this_company_template",
  "additional_information",
  "highest_qualification",
]);

const BOOLEAN_FIELDS = new Set<keyof ApplicationAnswers>(["willing_to_relocate"]);
const NUMBER_FIELDS = new Set<keyof ApplicationAnswers>(["notice_period_days", "total_experience_years"]);

export default function ProfilePage() {
  const [data, setData] = useState<ProfileResponse | null>(null);
  const [draft, setDraft] = useState<Partial<ApplicationAnswers>>({});
  const [voiceDraft, setVoiceDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await profileApi.get();
      setData(next);
      setDraft({});
      setVoiceDraft(null);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Couldn't load your profile.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const answers = data?.answers;
  const dirty = Object.keys(draft).length > 0 || voiceDraft !== null;

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      if (Object.keys(draft).length > 0) await profileApi.updateAnswers(draft);
      if (voiceDraft !== null) await profileApi.updateVoice(voiceDraft);
      await load();
      setSaved("Saved to disk.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  }

  function valueOf(field: keyof ApplicationAnswers): unknown {
    return field in draft ? draft[field] : answers?.[field];
  }

  if (error && !data) return <ErrorNote message={error} />;
  if (!answers) return <p style={{ color: "var(--ink-muted)" }}>Loading…</p>;

  return (
    <div className="space-y-5">
      {error && <ErrorNote message={error} />}

      <Card>
        <Eyebrow>
          {data!.ready_to_apply
            ? "Ready to apply"
            : `${data!.missing.length} answers still needed before CareerOS can apply`}
        </Eyebrow>
        {data!.ready_to_apply ? (
          <p className="text-sm" style={{ color: "var(--ink-secondary)" }}>
            Nothing outstanding. Pick jobs on the shortlist and CareerOS can submit them.
          </p>
        ) : (
          <>
            <p className="mb-3 max-w-2xl text-sm" style={{ color: "var(--ink-secondary)" }}>
              CareerOS won&apos;t guess these. It refuses to submit an application while any are unanswered,
              because sending an invented notice period or salary to a real employer is worse than not applying.
            </p>
            <ul className="flex flex-wrap gap-2">
              {data!.missing.map((field) => (
                <li
                  key={field}
                  className="rounded px-2 py-1 text-xs"
                  style={{ color: "var(--ink)", boxShadow: "inset 0 0 0 1px var(--status-warning)" }}
                >
                  {LABELS[field as keyof ApplicationAnswers] ?? field}
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      {SECTIONS.map((section) => (
        <Card key={section.title}>
          <Eyebrow>{section.title}</Eyebrow>
          {section.note && (
            <p className="-mt-1 mb-4 text-xs" style={{ color: "var(--ink-muted)" }}>
              {section.note}
            </p>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {section.fields.map((field) => (
              <Field
                key={field}
                name={field}
                label={LABELS[field] ?? field}
                value={valueOf(field)}
                onChange={(next) => setDraft((prev) => ({ ...prev, [field]: next }))}
              />
            ))}
          </div>
        </Card>
      ))}

      <Card>
        <Eyebrow>Cover letter voice</Eyebrow>
        <p className="-mt-1 mb-3 max-w-2xl text-xs" style={{ color: "var(--ink-muted)" }}>
          How letters should sound and what to emphasise. This shapes framing only — facts still come from your
          achievement bank, so nothing here can introduce a claim you can&apos;t back up.
        </p>
        <textarea
          value={voiceDraft ?? data!.voice}
          onChange={(event) => setVoiceDraft(event.target.value)}
          rows={16}
          spellCheck={false}
          className="w-full rounded-md p-3 font-mono text-xs leading-relaxed"
          style={{ background: "var(--surface-raised)", color: "var(--ink)", boxShadow: "inset 0 0 0 1px var(--ring)" }}
        />
      </Card>

      <Card>
        <Eyebrow>Work authorisation</Eyebrow>
        <p className="-mt-1 mb-3 max-w-2xl text-xs" style={{ color: "var(--ink-muted)" }}>
          This drives job discovery: only regions marked <code>citizen_or_permanent</code> are searched, which is
          why US postings get filtered out entirely rather than scored and shortlisted uselessly. Edit in{" "}
          <code>backend/config/application_answers.yaml</code>.
        </p>
        <ul className="space-y-1 text-sm">
          {Object.entries(answers.work_authorisation).map(([region, statusValue]) => (
            <li key={region} className="flex items-baseline justify-between gap-4">
              <span style={{ color: "var(--ink-secondary)" }}>{region.replace(/_/g, " ")}</span>
              <span
                className="text-xs"
                style={{
                  color:
                    statusValue === "citizen_or_permanent" ? "var(--status-good)" : "var(--ink-muted)",
                }}
              >
                {statusValue.replace(/_/g, " ")}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <div
        className="sticky bottom-0 flex flex-wrap items-center gap-3 rounded-lg px-4 py-3"
        style={{ background: "var(--surface)", boxShadow: "inset 0 0 0 1px var(--ring)" }}
      >
        <Button onClick={save} disabled={busy || !dirty}>
          {busy ? "Saving…" : dirty ? "Save changes" : "No changes"}
        </Button>
        <Button variant="quiet" onClick={() => void load()} disabled={busy}>
          Reload from disk
        </Button>
        {saved && (
          <span className="text-xs" style={{ color: "var(--status-good)" }}>
            {saved}
          </span>
        )}
        <span className="ml-auto text-xs" style={{ color: "var(--ink-muted)" }}>
          {data!.achievement_count} achievements in your bank
        </span>
      </div>
    </div>
  );
}

function Field({
  name,
  label,
  value,
  onChange,
}: {
  name: keyof ApplicationAnswers;
  label: string;
  value: unknown;
  onChange: (next: unknown) => void;
}) {
  const unanswered = isUnanswered(value);
  const fieldStyle = {
    background: "var(--surface-raised)",
    color: "var(--ink)",
    // A still-unanswered field is ringed in warning so it reads differently from one deliberately left blank.
    boxShadow: `inset 0 0 0 1px ${unanswered ? "var(--status-warning)" : "var(--ring)"}`,
  };

  return (
    <label className={LONG_FIELDS.has(name) ? "md:col-span-2" : undefined}>
      <span className="mb-1 flex items-baseline gap-2 text-xs" style={{ color: "var(--ink-secondary)" }}>
        {label}
        {unanswered && (
          <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--status-warning)" }}>
            needs you
          </span>
        )}
      </span>

      {BOOLEAN_FIELDS.has(name) ? (
        <select
          value={value === true ? "true" : value === false ? "false" : ""}
          onChange={(event) =>
            onChange(event.target.value === "" ? null : event.target.value === "true")
          }
          className="w-full rounded-md px-2.5 py-1.5 text-sm"
          style={fieldStyle}
        >
          <option value="">Not answered</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      ) : LONG_FIELDS.has(name) ? (
        <textarea
          value={unanswered && value !== "" ? "" : String(value ?? "")}
          onChange={(event) => onChange(event.target.value)}
          rows={3}
          className="w-full rounded-md px-2.5 py-1.5 text-sm"
          style={fieldStyle}
        />
      ) : (
        <input
          type={NUMBER_FIELDS.has(name) ? "number" : "text"}
          value={unanswered && value !== "" ? "" : String(value ?? "")}
          onChange={(event) => {
            const raw = event.target.value;
            if (!NUMBER_FIELDS.has(name)) return onChange(raw);
            onChange(raw === "" ? null : Number(raw));
          }}
          className="w-full rounded-md px-2.5 py-1.5 text-sm"
          style={fieldStyle}
        />
      )}
    </label>
  );
}
