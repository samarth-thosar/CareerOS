"""Loads and saves config/application_answers.yaml.

Round-trips rather than read-only, because the dashboard edits these values. Saving rewrites the file so the
YAML stays the source of truth a human can also edit directly -- there is no second copy to drift.

`TODO` in the file maps to the domain's PLACEHOLDER sentinel, so "the user hasn't filled this in" survives the
trip in both directions instead of degrading into an empty string.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from careeros.domain.candidate.application_answers import PLACEHOLDER, ApplicationAnswers

DEFAULT_ANSWERS_PATH = Path(__file__).resolve().parents[4] / "config" / "application_answers.yaml"

VOICE_PATH = Path(__file__).resolve().parents[4] / "data" / "master" / "voice.md"


class AnswersConfigError(ValueError):
    """Raised when the answers file is unreadable or structurally wrong."""


def _to_optional_int(value: Any) -> int | None:
    if value is None or value == PLACEHOLDER or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise AnswersConfigError(f"Expected a whole number, got {value!r}") from error


def _to_optional_float(value: Any) -> float | None:
    if value is None or value == PLACEHOLDER or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise AnswersConfigError(f"Expected a number, got {value!r}") from error


def _to_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == PLACEHOLDER or value == "":
        return None
    lowered = str(value).strip().lower()
    if lowered in {"true", "yes", "y", "1"}:
        return True
    if lowered in {"false", "no", "n", "0"}:
        return False
    raise AnswersConfigError(f"Expected true or false, got {value!r}")


def _text(value: Any, default: str = PLACEHOLDER) -> str:
    if value is None:
        return default
    return str(value).strip()


def load_answers(path: Path | None = None) -> ApplicationAnswers:
    answers_path = path or DEFAULT_ANSWERS_PATH
    if not answers_path.exists():
        # An absent file is not fatal: it means nothing has been filled in yet, which the all-placeholder
        # default represents accurately.
        return ApplicationAnswers()

    with answers_path.open("r", encoding="utf-8") as handle:
        raw: Any = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise AnswersConfigError(f"{answers_path} must contain a YAML mapping")

    authorisation = raw.get("work_authorisation") or {}
    if not isinstance(authorisation, dict):
        raise AnswersConfigError("'work_authorisation' must be a mapping of region -> status")

    return ApplicationAnswers(
        full_name=_text(raw.get("full_name")),
        email=_text(raw.get("email")),
        phone=_text(raw.get("phone")),
        current_location=_text(raw.get("current_location")),
        linkedin_url=_text(raw.get("linkedin_url")),
        github_url=_text(raw.get("github_url")),
        portfolio_url=_text(raw.get("portfolio_url"), default=""),
        work_authorisation={str(k): str(v) for k, v in authorisation.items()},
        requires_visa_sponsorship=bool(raw.get("requires_visa_sponsorship", True)),
        notice_period_days=_to_optional_int(raw.get("notice_period_days")),
        earliest_start_date=_text(raw.get("earliest_start_date")),
        willing_to_relocate=_to_optional_bool(raw.get("willing_to_relocate")),
        preferred_work_arrangement=_text(raw.get("preferred_work_arrangement")),
        current_ctc=_text(raw.get("current_ctc"), default=""),
        expected_ctc=_text(raw.get("expected_ctc")),
        salary_currency=_text(raw.get("salary_currency"), default="INR"),
        total_experience_years=_to_optional_float(raw.get("total_experience_years")),
        highest_qualification=_text(raw.get("highest_qualification")),
        gender=_text(raw.get("gender"), default=""),
        ethnicity=_text(raw.get("ethnicity"), default=""),
        disability_status=_text(raw.get("disability_status"), default=""),
        veteran_status=_text(raw.get("veteran_status"), default=""),
        why_this_company_template=_text(raw.get("why_this_company_template")),
        additional_information=_text(raw.get("additional_information"), default=""),
    )


def save_answers(answers: ApplicationAnswers, path: Path | None = None) -> Path:
    """Write answers back to YAML, keeping it hand-editable.

    Unset optional values are written as empty strings and unset required ones as TODO, so a round trip through
    the dashboard never silently converts "not answered yet" into "answered blank".
    """
    answers_path = path or DEFAULT_ANSWERS_PATH
    payload = {
        "full_name": answers.full_name,
        "email": answers.email,
        "phone": answers.phone,
        "current_location": answers.current_location,
        "linkedin_url": answers.linkedin_url,
        "github_url": answers.github_url,
        "portfolio_url": answers.portfolio_url,
        "work_authorisation": answers.work_authorisation,
        "requires_visa_sponsorship": answers.requires_visa_sponsorship,
        "notice_period_days": answers.notice_period_days if answers.notice_period_days is not None else PLACEHOLDER,
        "earliest_start_date": answers.earliest_start_date,
        "willing_to_relocate": (
            answers.willing_to_relocate if answers.willing_to_relocate is not None else PLACEHOLDER
        ),
        "preferred_work_arrangement": answers.preferred_work_arrangement,
        "salary_currency": answers.salary_currency,
        "current_ctc": answers.current_ctc,
        "expected_ctc": answers.expected_ctc,
        "total_experience_years": (
            answers.total_experience_years if answers.total_experience_years is not None else PLACEHOLDER
        ),
        "highest_qualification": answers.highest_qualification,
        "gender": answers.gender,
        "ethnicity": answers.ethnicity,
        "disability_status": answers.disability_status,
        "veteran_status": answers.veteran_status,
        "why_this_company_template": answers.why_this_company_template,
        "additional_information": answers.additional_information,
    }
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    with answers_path.open("w", encoding="utf-8") as handle:
        handle.write("# Answers for job application forms. Edited via the dashboard at /profile, or by hand.\n")
        handle.write("# TODO means CareerOS is waiting on you; it will refuse to submit while any remain.\n\n")
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return answers_path


def load_voice(path: Path | None = None) -> str:
    """The cover-letter voice guide. Absent means "use the model's default register"."""
    voice_path = path or VOICE_PATH
    return voice_path.read_text(encoding="utf-8") if voice_path.exists() else ""


def save_voice(content: str, path: Path | None = None) -> Path:
    voice_path = path or VOICE_PATH
    voice_path.parent.mkdir(parents=True, exist_ok=True)
    voice_path.write_text(content, encoding="utf-8")
    return voice_path
