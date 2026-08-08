/**
 * Typed client for the CareerOS API.
 *
 * Types mirror the backend DTOs rather than the domain entities, which is the point of having DTOs: the
 * dashboard is coupled to a deliberate response shape, not to the aggregates behind it.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type RemoteType = "remote" | "hybrid" | "onsite" | "unknown";

export type ApplicationStatus =
  | "found"
  | "interested"
  | "saved"
  | "resume_generated"
  | "applied"
  | "interview"
  | "assessment"
  | "recruiter_contact"
  | "rejected"
  | "offer"
  | "archived";

/** The six dimensions the model rates. Order is fixed so the score strip reads the same on every row. */
export const SCORE_DIMENSIONS = [
  { key: "resume_match", label: "Resume" },
  { key: "skill_area_fit", label: "Skills" },
  { key: "career_progression_fit", label: "Level" },
  { key: "remote_fit", label: "Remote" },
  { key: "salary_fit", label: "Salary" },
  { key: "company_quality", label: "Company" },
] as const;

export type ScoreDimensionKey = (typeof SCORE_DIMENSIONS)[number]["key"];

export interface ScoreDetail extends Record<ScoreDimensionKey, number> {
  value: number;
  narrative: string;
  model_used: string;
  strategy_version: string;
}

export interface JobSummary {
  id: string;
  source: string;
  title: string;
  company_name: string;
  url: string;
  location: string | null;
  remote_type: RemoteType;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_is_estimated: boolean;
  skills: string[];
  posting_date: string | null;
  discovered_at: string;
  status: ApplicationStatus | null;
  score: number | null;
  score_detail: ScoreDetail | null;
}

export interface JobDetail extends JobSummary {
  description: string;
}

export interface JobListResponse {
  total: number;
  matched: number;
  scored: number;
  items: JobSummary[];
}

export interface Overview {
  jobs_total: number;
  jobs_scored: number;
  jobs_unscored: number;
  companies: number;
  applications_by_status: Record<string, number>;
  resume_versions: number;
  pending_gaps: number;
  shortlist_size: number;
  shortlist_threshold: number;
  top_score: number | null;
  median_score: number | null;
}

export interface Count {
  label: string;
  value: number;
}

export interface Breakdowns {
  score_distribution: { floor: number; count: number }[];
  top_technologies: Count[];
  top_companies: Count[];
  remote_split: Count[];
  discovery_by_day: Count[];
}

export interface TimelineEntry {
  from_status: string | null;
  to_status: string;
  changed_at: string;
  reason: string | null;
  actor: string;
}

export interface ApplicationSummary {
  id: string;
  job_id: string;
  job_title: string;
  company_name: string;
  job_url: string;
  status: ApplicationStatus;
  applied_at: string | null;
  score: number | null;
  timeline: TimelineEntry[];
}

export interface ApplicationListResponse {
  counts_by_status: Record<string, number>;
  items: ApplicationSummary[];
}

export interface GapFlag {
  id: string;
  resume_version_id: string;
  job_id: string;
  missing_skill_or_requirement: string;
  suggested_language: string | null;
  status: string;
}

export interface ResumeVersion {
  id: string;
  created_at: string;
  master_version_ref: string;
  render_status: "draft" | "rendered";
  pdf_path: string | null;
  has_gaps: boolean;
  diff_summary: string | null;
}

export interface TailorOutcome {
  resume_version_id: string;
  artifact_directory: string;
  pdf_rendered: boolean;
  pdf_unavailable: boolean;
  gap_count: number;
  pdf_note?: string;
}

/** Thrown with the backend's own message, so the UI can say what went wrong rather than "request failed". */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(`Can't reach the backend at ${API_BASE_URL}. Is it running?`, 0);
  }

  if (!response.ok) {
    // FastAPI puts the useful text in `detail`; fall back to the status line if it's shaped differently.
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the status line */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export interface JobQuery {
  limit?: number;
  offset?: number;
  ranked?: boolean;
  minScore?: number;
  search?: string;
  company?: string;
  source?: string;
  remoteType?: string;
  technology?: string;
  status?: string;
  unscoredOnly?: boolean;
}

function toQueryString(query: JobQuery): string {
  const params = new URLSearchParams();
  const mapping: Record<string, unknown> = {
    limit: query.limit,
    offset: query.offset,
    ranked: query.ranked,
    min_score: query.minScore,
    search: query.search,
    company: query.company,
    source: query.source,
    remote_type: query.remoteType,
    technology: query.technology,
    status: query.status,
    unscored_only: query.unscoredOnly,
  };
  for (const [key, value] of Object.entries(mapping)) {
    // Skip empties so a cleared filter disappears from the URL instead of sending "".
    if (value === undefined || value === null || value === "" || value === false) continue;
    params.set(key, String(value));
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  baseUrl: API_BASE_URL,

  health: () => request<{ status: string }>("/health"),

  jobs: (query: JobQuery = {}) => request<JobListResponse>(`/jobs${toQueryString(query)}`),
  job: (jobId: string) => request<JobDetail>(`/jobs/${jobId}`),
  discover: () =>
    request<{ providers_run: string[]; new_jobs: Record<string, number> }>("/jobs/discover", {
      method: "POST",
    }),

  overview: () => request<Overview>("/analytics/overview"),
  breakdowns: () => request<Breakdowns>("/analytics/breakdowns"),

  applications: (limit = 200) => request<ApplicationListResponse>(`/applications?limit=${limit}`),

  scoreBatch: (limit?: number) =>
    request<{ scored: number; failed: number; remaining: number }>(
      `/scoring/run${limit ? `?limit=${limit}` : ""}`,
      { method: "POST" },
    ),

  tailor: (jobId: string) => request<TailorOutcome>(`/resumes/tailor/${jobId}`, { method: "POST" }),
  resumeVersions: (jobId: string) =>
    request<{ count: number; items: ResumeVersion[] }>(`/resumes/versions/${jobId}`),
  gaps: () => request<{ count: number; items: GapFlag[] }>("/resumes/gaps"),
};
