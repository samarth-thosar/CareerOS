"use client";

/**
 * Shared primitives.
 *
 * Status uses the reserved status palette and always pairs the colour with the label text, so state is never
 * communicated by colour alone -- two of these steps sit below 3:1 on the light surface by design, and the
 * label is the mitigation.
 */

import type { ApplicationStatus } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  found: "var(--ink-muted)",
  interested: "var(--accent)",
  saved: "var(--score-3)",
  resume_generated: "var(--score-5)",
  applied: "var(--status-good)",
  interview: "var(--status-good)",
  assessment: "var(--status-warning)",
  recruiter_contact: "var(--status-warning)",
  offer: "var(--status-good)",
  rejected: "var(--status-critical)",
  archived: "var(--ink-muted)",
};

function humanise(status: string): string {
  return status.replace(/_/g, " ");
}

export function StatusPill({ status }: { status: ApplicationStatus | string | null }) {
  if (!status) return <span style={{ color: "var(--ink-muted)" }}>untracked</span>;
  const color = STATUS_COLOR[status] ?? "var(--ink-muted)";
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs">
      <span aria-hidden className="size-2 shrink-0 rounded-full" style={{ background: color }} />
      <span style={{ color: "var(--ink-secondary)" }}>{humanise(status)}</span>
    </span>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg p-5 ${className}`}
      style={{ background: "var(--surface)", boxShadow: `inset 0 0 0 1px var(--ring)` }}
    >
      {children}
    </section>
  );
}

/** An eyebrow label. Used to name a region, not to decorate one. */
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em]"
      style={{ color: "var(--ink-muted)" }}
    >
      {children}
    </h2>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "quiet";
  type?: "button" | "submit";
}) {
  const primary = variant === "primary";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="rounded-md px-3 py-1.5 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
      style={
        primary
          ? { background: "var(--accent)", color: "#ffffff" }
          : { color: "var(--ink-secondary)", boxShadow: `inset 0 0 0 1px var(--ring)` }
      }
    >
      {children}
    </button>
  );
}

/** Empty states are an invitation to act, so each one names the next step rather than just reporting nothing. */
export function EmptyState({ title, action }: { title: string; action?: string }) {
  return (
    <div className="py-10 text-center">
      <p className="text-sm" style={{ color: "var(--ink-secondary)" }}>
        {title}
      </p>
      {action && (
        <p className="mt-1 text-xs" style={{ color: "var(--ink-muted)" }}>
          {action}
        </p>
      )}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      className="rounded-md px-4 py-3 text-sm"
      style={{ color: "var(--ink)", boxShadow: `inset 0 0 0 1px var(--status-critical)` }}
      role="alert"
    >
      <span aria-hidden className="mr-2">
        !
      </span>
      {message}
    </div>
  );
}

/**
 * A horizontal bar list -- the right form for "top N by count", which is a magnitude comparison across a short
 * ranked list. Values are labelled directly, so no legend and no axis are needed.
 */
export function BarList({ items, emptyLabel }: { items: { label: string; value: number }[]; emptyLabel: string }) {
  if (items.length === 0) return <EmptyState title={emptyLabel} />;
  const max = Math.max(...items.map((item) => item.value), 1);

  return (
    <ol className="space-y-2">
      {items.map((item) => (
        <li key={item.label} className="grid grid-cols-[1fr_auto] items-center gap-3">
          <div className="min-w-0">
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <span className="truncate text-sm" style={{ color: "var(--ink-secondary)" }}>
                {item.label}
              </span>
              <span className="tnum text-xs" style={{ color: "var(--ink-muted)" }}>
                {item.value}
              </span>
            </div>
            <div className="h-[6px] w-full overflow-hidden rounded-[3px]" style={{ background: "var(--hairline)" }}>
              <div
                className="h-full rounded-[3px]"
                style={{ width: `${(item.value / max) * 100}%`, background: "var(--score-3)" }}
              />
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

/**
 * Which board a job came from.
 *
 * Always shown, never abbreviated away: knowing a posting came from Greenhouse vs Wellfound vs a company page
 * changes how you read it (freshness, whether the apply flow is automatable, how much to trust the salary), so
 * it belongs on the row rather than behind a click.
 */
export function SourceBadge({ source }: { source: string }) {
  return (
    <span
      className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em]"
      style={{ color: "var(--ink-secondary)", boxShadow: "inset 0 0 0 1px var(--ring)" }}
      title={`Found on ${source}`}
    >
      {source}
    </span>
  );
}
