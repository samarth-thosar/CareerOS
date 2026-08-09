"""Profile endpoints: the candidate profile, the application answers, and the cover-letter voice.

All three are YAML/Markdown files a human can also edit by hand, and writes go straight back to those files
rather than into a second store. That keeps one source of truth: nothing to reconcile, and editing on disk while
the app runs is fine as long as the reload endpoint is hit afterwards.

`missing` is returned alongside the answers so the dashboard can show exactly what is still outstanding without
duplicating the definition of "outstanding".
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from careeros.domain.candidate.application_answers import ApplicationAnswers
from careeros.infrastructure.bootstrap import Container, in_session, seed_candidate_profile
from careeros.infrastructure.config.answers_loader import (
    AnswersConfigError,
    load_answers,
    load_voice,
    save_answers,
    save_voice,
)
from careeros.infrastructure.config.profile_loader import ProfileConfigError
from careeros.presentation.api.dependencies import get_container

router = APIRouter(tags=["profile"])

# Only these may be written through the API. Anything else in a request body is ignored rather than silently
# creating a field, so a typo cannot invent an answer the forms will never read.
_WRITABLE = {spec for spec in ApplicationAnswers.__dataclass_fields__}


@router.get("/profile")
async def get_profile(container: Annotated[Container, Depends(get_container)]) -> dict[str, Any]:
    """Everything the candidate can edit, plus what is still outstanding."""
    profile = await in_session(container, lambda services: services.candidate_profile.get())
    answers = container.answers
    return {
        "profile": asdict(profile) if profile else None,
        "answers": asdict(answers),
        "missing": answers.missing_fields(),
        "ready_to_apply": answers.ready_to_apply,
        "voice": container.voice,
        "achievement_count": len(container.achievement_bank.achievements) if container.achievement_bank else 0,
    }


@router.put("/profile/answers")
async def update_answers(
    container: Annotated[Container, Depends(get_container)],
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """Patch application answers. Only the supplied keys change; everything else keeps its current value."""
    current = asdict(container.answers)
    unknown = sorted(set(payload) - _WRITABLE)
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown fields: {unknown}")

    current.update({key: value for key, value in payload.items()})
    try:
        updated = ApplicationAnswers(**current)
        save_answers(updated)
        # Re-read rather than trusting the in-memory object, so the API reflects what is actually on disk.
        container.answers = load_answers()
    except (AnswersConfigError, TypeError, ValueError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    return {
        "answers": asdict(container.answers),
        "missing": container.answers.missing_fields(),
        "ready_to_apply": container.answers.ready_to_apply,
    }


@router.put("/profile/voice")
async def update_voice(
    container: Annotated[Container, Depends(get_container)],
    payload: Annotated[dict[str, str], Body()],
) -> dict[str, Any]:
    """Replace the cover-letter voice guide."""
    content = payload.get("voice")
    if content is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expected a 'voice' field")
    save_voice(content)
    container.voice = load_voice()
    return {"voice": container.voice}


@router.post("/profile/reload")
async def reload_profile(container: Annotated[Container, Depends(get_container)]) -> dict[str, Any]:
    """Re-read every candidate file from disk: profile, answers and voice.

    Explicit rather than automatic on boot, so a profile the Memory module has adjusted is never silently
    reverted by a stale file.
    """
    try:
        profile = await seed_candidate_profile(container)
    except ProfileConfigError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    try:
        container.answers = load_answers()
        container.voice = load_voice()
    except AnswersConfigError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    return {
        "profile": asdict(profile),
        "answers": asdict(container.answers),
        "missing": container.answers.missing_fields(),
        "ready_to_apply": container.answers.ready_to_apply,
    }
