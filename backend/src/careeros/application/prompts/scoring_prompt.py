"""Builds the job-scoring prompt.

Design: the model rates six dimensions independently; CareerOS combines them into the final 0-100 using the
weights from config. This split matters --

* the configured `scoring_weights` genuinely drive the result instead of being decoration,
* the arithmetic is auditable and reproducible, whereas a holistic number from an 8B model is neither,
* rating one narrow dimension is a much easier task than holistic judgment, so a small local model does it
  far more reliably,
* and Memory can retune weights later and recompute every historical score without re-running inference.

`SCORING_STRATEGY_VERSION` is stored on every Score. Bump it whenever this prompt or the combination formula
changes, so Memory can tell scores produced by different strategies apart rather than comparing across a
silent behavioral change.
"""
from __future__ import annotations

from careeros.application.ports.llm_provider import PromptSpec
from careeros.domain.candidate.candidate_profile import CandidateProfile
from careeros.domain.job.job import Job

SCORING_STRATEGY_VERSION = "1.0.0"

# Long descriptions are mostly boilerplate (benefits, EEO statements) and cost inference time on a local
# model, so the tail is dropped. The signal for fit is near the top of virtually every posting.
MAX_DESCRIPTION_CHARS = 6_000

DIMENSIONS: tuple[str, ...] = (
    "resume_match",
    "skill_area_fit",
    "career_progression_fit",
    "remote_fit",
    "salary_fit",
    "company_quality",
)

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        **{dimension: {"type": "integer", "minimum": 0, "maximum": 100} for dimension in DIMENSIONS},
        "narrative": {"type": "string"},
    },
    "required": [*DIMENSIONS, "narrative"],
}

_SYSTEM_PROMPT = """\
You are a careful technical recruiter assessing how well a job fits one specific candidate.

Rate each dimension from 0 to 100, judging ONLY that dimension:

- resume_match: how well the candidate's stated skills and experience match what the job requires.
- skill_area_fit: whether the job sits in one of the candidate's target skill areas.
- career_progression_fit: whether this is a sensible next step. Penalise roles far below the candidate's
  level, and roles requiring substantially more experience than they have.
- remote_fit: how well the job's location and remote arrangement match the candidate's preference.
- salary_fit: how the pay compares to the candidate's floor. If the posting states no salary, return 50 to
  mean "unknown" -- do not guess.
- company_quality: reputation, engineering culture and stability, judged only from what the posting shows.
  If there is nothing to judge, return 50.

Rules:
- Judge only from the information given. Never invent experience the candidate has not listed.
- A role that is not a software/AI engineering role should score low on skill_area_fit and resume_match, even
  if the description mentions technologies the candidate knows.
- narrative: 2-4 sentences explaining the notable scores, naming the concrete evidence you used.

Reply with JSON only, matching the requested schema. No other text."""


def _format_profile(profile: CandidateProfile) -> str:
    preferences = profile.preferences
    roles = ", ".join(f"{role.title} (priority {role.priority}/5)" for role in profile.top_roles()) or "unspecified"
    lines = [
        f"Headline: {profile.headline or 'unspecified'}",
        f"Years of experience: {profile.years_experience if profile.years_experience is not None else 'unspecified'}",
        f"Summary: {profile.summary or 'unspecified'}",
        f"Skills: {', '.join(profile.skills) or 'unspecified'}",
        f"Target roles: {roles}",
    ]
    if preferences is not None:
        floor = f"{preferences.salary_floor:,.0f}" if preferences.salary_floor else "not specified"
        lines += [
            f"Remote preference: {preferences.remote_preference}",
            f"Preferred locations: {', '.join(preferences.preferred_locations) or 'any'}",
            f"Target skill areas: {', '.join(preferences.target_skill_areas) or 'unspecified'}",
            f"Minimum acceptable salary (per year): {floor}",
        ]
    return "\n".join(lines)


def _format_job(job: Job, company_name: str) -> str:
    salary = job.salary_range
    if salary.minimum is not None and salary.maximum is not None:
        estimated = " (parsed from the description, treat as approximate)" if salary.is_estimated else ""
        salary_text = f"{salary.currency or ''} {salary.minimum:,.0f}-{salary.maximum:,.0f}{estimated}".strip()
    else:
        salary_text = "not stated"

    location = ", ".join(part for part in (job.location.city, job.location.country) if part) or "unspecified"
    description = job.description[:MAX_DESCRIPTION_CHARS]
    if len(job.description) > MAX_DESCRIPTION_CHARS:
        description += "\n[description truncated]"

    return "\n".join(
        [
            f"Title: {job.title}",
            f"Company: {company_name}",
            f"Location: {location} (arrangement: {job.location.remote_type.value})",
            f"Salary: {salary_text}",
            f"Detected technologies: {', '.join(job.skills) or 'none detected'}",
            "Description:",
            description,
        ]
    )


def build_scoring_prompt(job: Job, company_name: str, profile: CandidateProfile) -> PromptSpec:
    """Assemble the scoring request for one job against the candidate profile."""
    user_prompt = (
        f"CANDIDATE\n{_format_profile(profile)}\n\n"
        f"JOB\n{_format_job(job, company_name)}\n\n"
        "Rate every dimension and return the JSON object."
    )
    return PromptSpec(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_schema=RESPONSE_SCHEMA,
        # Near-deterministic: the same job and profile should not score differently run to run.
        temperature=0.0,
    )
