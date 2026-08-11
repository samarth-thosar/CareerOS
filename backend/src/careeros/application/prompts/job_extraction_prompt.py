"""Extracts structured job fields from text the candidate pasted in.

Exists because some sites cannot be read programmatically and should not be. Wellfound sits behind Cloudflare
bot protection and forbids automated access; LinkedIn is similar. Rather than circumventing either, the candidate
browses those sites themselves, copies the posting, and pastes it here -- the reading is human, and everything
downstream (scoring, tailoring, cover letters, form drafting) works identically regardless of where a job came
from.

This is the one place the LLM is used for extraction rather than judgement, because pasted text is unstructured
by nature. It is asked only to *find* fields present in the text, never to infer or improve them: a guessed
company name or invented salary would corrupt the record this job is scored and applied from.
"""
from __future__ import annotations

from careeros.application.ports.llm_provider import PromptSpec

EXTRACTION_STRATEGY_VERSION = "1.0.0"

MAX_INPUT_CHARS = 12_000
MAX_OUTPUT_TOKENS = 700

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "company_name": {"type": "string"},
        "location": {"type": "string"},
        "salary_text": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["title", "company_name", "location", "description"],
}

_SYSTEM_PROMPT = """\
You extract structured fields from a job posting the user copied from a website.

Rules:
- Only report what the text actually says. If a field is not present, return an empty string for it -- never
  guess, never infer from context, never tidy a value into something it did not say.
- title: the role title exactly as written, without the company name or location appended.
- company_name: the hiring company. If the text names an agency posting on behalf of someone else, use the
  hiring company when it is stated, otherwise the name given.
- location: copy the location text verbatim, including any remote wording ("Remote - India", "Bangalore or
  Remote"). Do not normalise or expand it -- downstream code decides work eligibility from these exact words.
- salary_text: only if a pay figure or range is explicitly stated. Otherwise empty.
- description: the responsibilities and requirements. Strip navigation, cookie banners, "apply now" boilerplate
  and unrelated page furniture, but do not summarise or paraphrase the substance.

Reply with JSON only."""


def build_job_extraction_prompt(pasted_text: str) -> PromptSpec:
    text = pasted_text[:MAX_INPUT_CHARS]
    if len(pasted_text) > MAX_INPUT_CHARS:
        text += "\n[truncated]"

    return PromptSpec(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=f"JOB POSTING TEXT\n{text}\n\nExtract the fields and return the JSON object.",
        response_schema=RESPONSE_SCHEMA,
        # Extraction, not composition: any creativity here is a wrong answer.
        temperature=0.0,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
