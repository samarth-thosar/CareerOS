"use client";

/**
 * The score strip -- the element this dashboard is built around.
 *
 * CareerOS's differentiator is that a score comes with reasons, so the reasons belong on the row rather than
 * behind a click: six thin bars showing how each dimension contributed, readable at a glance while scanning.
 *
 * Colour choices follow from the data being a magnitude, not a set of categories: all six bars use the same
 * sequential blue and the bar's *length* carries the value. Giving each dimension its own hue would imply the
 * dimensions are unrelated identities and would need a six-colour categorical palette that cannot clear the
 * colourblind-separation floor. Labels distinguish them instead, so the encoding never depends on colour.
 */

import { SCORE_DIMENSIONS, type ScoreDetail } from "@/lib/api";

/** Sequential steps, darkening with value. Kept at or above the ordinal contrast floor for discrete bars. */
function stepFor(value: number): string {
  if (value >= 80) return "var(--score-5)";
  if (value >= 60) return "var(--accent)";
  if (value >= 40) return "var(--score-3)";
  if (value >= 20) return "var(--score-2)";
  return "var(--score-1)";
}

export function ScoreStrip({ detail, showLabels = false }: { detail: ScoreDetail; showLabels?: boolean }) {
  return (
    <div className="flex gap-3" role="list" aria-label="Score breakdown by dimension">
      {SCORE_DIMENSIONS.map(({ key, label }) => {
        const value = Math.round(detail[key]);
        return (
          <div key={key} role="listitem" className="min-w-0 flex-1" title={`${label}: ${value} of 100`}>
            {showLabels && (
              <div className="mb-1 flex items-baseline justify-between gap-1">
                <span className="truncate text-[11px]" style={{ color: "var(--ink-muted)" }}>
                  {label}
                </span>
                <span className="tnum text-[11px]" style={{ color: "var(--ink-secondary)" }}>
                  {value}
                </span>
              </div>
            )}
            {/* The track is the 100 baseline, so a short bar still reads as "out of 100". */}
            <div className="h-[6px] w-full overflow-hidden rounded-[3px]" style={{ background: "var(--hairline)" }}>
              <div
                className="h-full rounded-[3px]"
                style={{ width: `${Math.max(value, 2)}%`, background: stepFor(value) }}
              />
            </div>
            {!showLabels && <span className="sr-only">{`${label} ${value} of 100`}</span>}
          </div>
        );
      })}
    </div>
  );
}

/**
 * The score itself, sized to its role. `lg` is for the hero, where the number is the headline; `sm` is for
 * list rows, where it is one column among several.
 */
export function ScoreBadge({ score, size = "sm" }: { score: number | null; size?: "sm" | "lg" }) {
  if (score === null) {
    return (
      <span
        className={size === "lg" ? "text-5xl" : "text-sm"}
        style={{ color: "var(--ink-muted)" }}
        title="Not scored yet"
      >
        &mdash;
      </span>
    );
  }
  return (
    <span
      className={`tnum font-semibold tracking-tight ${size === "lg" ? "text-6xl" : "text-lg"}`}
      style={{ color: stepFor(score) }}
    >
      {score}
    </span>
  );
}
