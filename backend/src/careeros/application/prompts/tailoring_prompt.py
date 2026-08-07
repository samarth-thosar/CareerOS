"""Builds the resume-tailoring prompt.

The model is given the achievement bank and asked only to *choose*: which entries to include, which of their
existing bullets, in what order, and optionally a reworded version of each. It is never asked to write
experience, and it never sees or produces LaTeX.

That framing is what makes fabrication structurally hard rather than merely discouraged. Even so the output is
validated (`domain.resume.tailoring.validate_plan`) rather than trusted -- the prompt states the rules, the
validator enforces them.
"""
from __future__ import annotations

from careeros.application.ports.llm_provider import PromptSpec
from careeros.domain.candidate.candidate_profile import CandidateProfile
from careeros.domain.job.job import Job
from careeros.domain.resume.achievement import AchievementBank

TAILORING_STRATEGY_VERSION = "1.0.0"

MAX_DESCRIPTION_CHARS = 6_000

# Generous because the response repeats every selected bullet, and bullets are long. Truncation surfaces as
# unparseable JSON, so under-budgeting here is worse than over-budgeting.
MAX_OUTPUT_TOKENS = 3_000

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "achievements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "bullets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_index": {"type": "integer", "minimum": 0},
                                "rephrased": {"type": "string"},
                            },
                            "required": ["source_index"],
                        },
                    },
                },
                "required": ["id", "bullets"],
            },
        },
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "skills", "achievements", "gaps"],
}

_SYSTEM_PROMPT = """\
You tailor a candidate's resume to one job by SELECTING from content they have already written. You are not
writing a resume and you are not inventing anything.

Hard rules -- violating any of these makes your whole response unusable:
- Only use achievement ids that appear in the ACHIEVEMENT BANK. Never invent an id.
- Only use source_index values that exist for that achievement. Indices are 0-based.
- Only list skills the candidate already claims (from their skills list or the technologies in the bank).
- If you reword a bullet, you may shorten it, re-emphasise it, or change wording to match the job's language.
  You may NOT add facts, and you may NOT introduce any number, percentage or metric that is not already in the
  original bullet. Omit "rephrased" entirely to use the original text unchanged.
- Bullets use **double asterisks** for emphasis. Keep those markers on the same key terms when you reword, and
  do not add emphasis to new terms. If you are not actually changing the wording, omit "rephrased" rather than
  echoing the sentence back.

What to produce:
- achievements: the entries worth including for THIS job, most relevant first, each with the bullets to show
  (also most relevant first). Prefer entries whose technologies overlap the job. Leave out entries that add
  nothing for this role.
- skills: the candidate's existing skills that matter for this job, most relevant first.
- summary: 2-3 sentences positioning the candidate for this specific role, using only facts visible in their
  profile and bank.
- gaps: requirements the job asks for that the candidate's bank genuinely cannot support. Be specific and
  honest -- this is how the candidate learns what to add, so do not pad it and do not hide real gaps.

Reply with JSON only, matching the requested schema. No other text."""


def _format_bank(bank: AchievementBank) -> str:
    blocks: list[str] = []
    for achievement in bank.achievements:
        header = f"id: {achievement.id} | kind: {achievement.kind.value} | title: {achievement.title}"
        if achievement.organization:
            header += f" | organization: {achievement.organization}"
        if achievement.technologies:
            header += f" | technologies: {', '.join(achievement.technologies)}"
        bullets = "\n".join(
            f"    [{index}] {bullet}" for index, bullet in enumerate(achievement.bullets)
        )
        blocks.append(f"{header}\n  bullets:\n{bullets}")
    return "\n\n".join(blocks)


def _format_job(job: Job, company_name: str) -> str:
    description = job.description[:MAX_DESCRIPTION_CHARS]
    if len(job.description) > MAX_DESCRIPTION_CHARS:
        description += "\n[description truncated]"
    return "\n".join(
        [
            f"Title: {job.title}",
            f"Company: {company_name}",
            f"Detected technologies: {', '.join(job.skills) or 'none detected'}",
            "Description:",
            description,
        ]
    )


def build_tailoring_prompt(
    job: Job, company_name: str, profile: CandidateProfile, bank: AchievementBank
) -> PromptSpec:
    user_prompt = (
        f"CANDIDATE\n"
        f"Headline: {profile.headline or 'unspecified'}\n"
        f"Years of experience: {profile.years_experience if profile.years_experience is not None else 'unspecified'}\n"
        f"Summary: {profile.summary or 'unspecified'}\n"
        f"Claimable skills: {', '.join(profile.skills) or 'unspecified'}\n\n"
        f"ACHIEVEMENT BANK\n{_format_bank(bank)}\n\n"
        f"JOB\n{_format_job(job, company_name)}\n\n"
        "Select the content for this job and return the JSON object."
    )
    return PromptSpec(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_schema=RESPONSE_SCHEMA,
        # Slightly above zero: rewording benefits from a little flexibility, selection is constrained anyway.
        temperature=0.2,
        # Tailoring echoes selected bullets back, so its output scales with the bank. The default budget
        # suits scoring and silently truncated this response into unparseable JSON.
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
