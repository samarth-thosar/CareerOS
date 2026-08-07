"""Resume tailoring endpoints."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from careeros.application.services.resume_manager_service import TailoringResponseError
from careeros.domain.resume.achievement import UnknownAchievementError, UnknownBulletError
from careeros.domain.resume.tailoring import FabricationError
from careeros.infrastructure.bootstrap import Container, in_session
from careeros.infrastructure.resume.achievement_loader import (
    AchievementBankError,
    load_achievement_bank,
)
from careeros.presentation.api.dependencies import get_container

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("/tailor/{job_id}")
async def tailor_resume(
    job_id: str,
    container: Annotated[Container, Depends(get_container)],
) -> dict[str, Any]:
    """Tailor the master resume for one job, writing a new version and artifact folder.

    Never overwrites a previous version. Returns 422 if the model tried to claim anything the achievement bank
    does not support -- that is a refusal to fabricate, not a transient failure.
    """
    if container.achievement_bank is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No achievement bank loaded; fix data/master/achievements.yaml and POST /resumes/bank/reload",
        )

    try:
        outcome = await in_session(container, lambda s: s.resume_manager.tailor_for_job(job_id))
    except (FabricationError, UnknownAchievementError, UnknownBulletError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Refused to fabricate: {error}") from error
    except (TailoringResponseError, LookupError, RuntimeError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    payload = asdict(outcome)
    payload["artifact_directory"] = str(outcome.artifact_directory)
    if outcome.pdf_unavailable:
        payload["pdf_note"] = (
            "No LaTeX engine on PATH, so only resume.tex was written. Install tectonic (smallest), "
            "or MiKTeX/TeX Live, to get PDFs."
        )
    return payload


@router.get("/bank")
async def get_achievement_bank(container: Annotated[Container, Depends(get_container)]) -> dict[str, Any]:
    """The achievement bank tailoring may draw from -- the full set of claimable content."""
    bank = container.achievement_bank
    if bank is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No achievement bank loaded")
    return {
        "count": len(bank.achievements),
        "technologies": bank.all_technologies(),
        "achievements": [asdict(achievement) for achievement in bank.achievements],
    }


@router.post("/bank/reload")
async def reload_achievement_bank(
    container: Annotated[Container, Depends(get_container)],
) -> dict[str, Any]:
    """Re-read data/master/achievements.yaml after editing it, without restarting."""
    try:
        bank = load_achievement_bank()
    except AchievementBankError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    container.achievement_bank = bank
    return {"count": len(bank.achievements), "ids": sorted(bank.ids)}


@router.get("/gaps")
async def list_gaps(container: Annotated[Container, Depends(get_container)]) -> dict[str, Any]:
    """Requirements the achievement bank could not support, awaiting a decision from you."""
    if container.achievement_bank is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No achievement bank loaded")
    flags = await in_session(container, lambda s: s.resume_manager.list_pending_gaps())
    return {"count": len(flags), "items": [asdict(flag) for flag in flags]}


@router.get("/versions/{job_id}")
async def list_versions(
    job_id: str,
    container: Annotated[Container, Depends(get_container)],
) -> dict[str, Any]:
    """Every resume version generated for a job, newest first."""
    if container.achievement_bank is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No achievement bank loaded")
    versions = await in_session(container, lambda s: s.resume_manager.versions_for_job(job_id))
    return {
        "count": len(versions),
        "items": [
            {
                "id": version.id,
                "created_at": version.created_at,
                "master_version_ref": version.source_master_version_ref,
                "render_status": version.render_status.value,
                "pdf_path": version.pdf_path,
                "has_gaps": version.has_gaps,
                "diff_summary": version.diff_summary,
            }
            for version in versions
        ],
    }
