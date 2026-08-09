"""Builds the cover-letter prompt.

Same anti-fabrication stance as resume tailoring, adapted to prose. A cover letter is generated text, so it
cannot be constrained to selecting ids -- but it can be constrained in what it is *allowed to know*: the model
sees only the achievement bank, the profile, and the candidate's own voice notes. Anything not in those is not
available to assert, and the output is checked afterwards for invented figures.

The voice file supplies framing, never facts. That split is deliberate: it lets the candidate control how the
letter sounds without giving them a place to accidentally introduce claims the bank cannot support.
"""
from __future__ import annotations

from careeros.application.ports.llm_provider import PromptSpec
from careeros.domain.candidate.application_answers import PLACEHOLDER, ApplicationAnswers
from careeros.domain.candidate.candidate_profile import CandidateProfile
from careeros.domain.job.job import Job
from careeros.domain.resume.achievement import AchievementBank

COVER_LETTER_STRATEGY_VERSION = "1.0.0"

MAX_DESCRIPTION_CHARS = 4_000
MAX_OUTPUT_TOKENS = 1_200

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "body": {"type": "string"},
        "achievements_referenced": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["body", "achievements_referenced", "gaps"],
}

_SYSTEM_PROMPT = """\
You write a cover letter for one candidate and one job, using only the facts you are given.

Hard rules:
- Every claim must trace to the ACHIEVEMENT BANK or the CANDIDATE section. If it is not there, you may not say it.
- Never introduce a number, percentage, duration or scale that is not already in the material you were given.
- Never claim a technology the candidate has not listed.
- Do not invent enthusiasm for the company beyond what the job description and the candidate's own notes support.
- If the job needs something the candidate cannot support, do not paper over it. List it under "gaps".

Style:
- Three or four short paragraphs. No greeting line, no sign-off -- those are added around your text.
- Open with why this specific role, not a generic statement about yourself.
- Go deep on one or two achievements rather than listing everything. Name what was actually hard.
- Plain, direct sentences. No superlatives about yourself, no "passionate", no "results-driven".
- Follow the VOICE section when it says something; ignore any part of it still marked TODO.

Return JSON only:
- body: the letter text, paragraphs separated by blank lines.
- achievements_referenced: the ids of bank entries you actually drew on.
- gaps: requirements the candidate genuinely cannot support, or an empty list."""


def _usable(value: str) -> str | None:
    """Placeholders and blanks are absent, not content -- never pass "TODO" to the model as if it were data."""
    cleaned = (value or "").strip()
    if not cleaned or cleaned == PLACEHOLDER:
        return None
    return cleaned


def _format_voice(voice: str) -> str:
    """Strip TODO lines so unfilled prompts are not read as instructions."""
    if not voice.strip():
        return "Not specified -- use a direct, concrete register."
    kept = [line for line in voice.splitlines() if PLACEHOLDER not in line]
    collapsed = "\n".join(kept).strip()
    return collapsed or "Not specified -- use a direct, concrete register."


def _format_bank(bank: AchievementBank) -> str:
    blocks = []
    for achievement in bank.achievements:
        header = f"id: {achievement.id} | {achievement.title}"
        if achievement.organization:
            header += f" at {achievement.organization}"
        if achievement.technologies:
            header += f" | {', '.join(achievement.technologies)}"
        bullets = "\n".join(f"    - {bullet}" for bullet in achievement.bullets)
        blocks.append(f"{header}\n{bullets}")
    return "\n\n".join(blocks)


def build_cover_letter_prompt(
    job: Job,
    company_name: str,
    profile: CandidateProfile,
    answers: ApplicationAnswers,
    bank: AchievementBank,
    voice: str,
) -> PromptSpec:
    description = job.description[:MAX_DESCRIPTION_CHARS]
    if len(job.description) > MAX_DESCRIPTION_CHARS:
        description += "\n[truncated]"

    why = _usable(answers.why_this_company_template)
    candidate_lines = [
        f"Name: {_usable(answers.full_name) or 'unspecified'}",
        f"Headline: {profile.headline or 'unspecified'}",
        f"Years of experience: {profile.years_experience if profile.years_experience is not None else 'unspecified'}",
        f"Summary: {profile.summary or 'unspecified'}",
        f"Claimable skills: {', '.join(profile.skills) or 'unspecified'}",
        f"Based in: {_usable(answers.current_location) or 'unspecified'}",
    ]
    if why:
        candidate_lines.append(f"What they want out of a role, in their words: {why}")

    user_prompt = (
        f"CANDIDATE\n" + "\n".join(candidate_lines) + "\n\n"
        f"VOICE\n{_format_voice(voice)}\n\n"
        f"ACHIEVEMENT BANK (the only facts you may assert)\n{_format_bank(bank)}\n\n"
        f"JOB\nTitle: {job.title}\nCompany: {company_name}\n"
        f"Detected technologies: {', '.join(job.skills) or 'none detected'}\n"
        f"Description:\n{description}\n\n"
        "Write the letter and return the JSON object."
    )

    return PromptSpec(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_schema=RESPONSE_SCHEMA,
        # Prose needs a little more freedom than selection does, but not enough to start embellishing.
        temperature=0.3,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
