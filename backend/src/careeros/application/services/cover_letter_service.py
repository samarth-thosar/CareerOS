"""CoverLetterService -- writes a cover letter for one job from the achievement bank.

Unlike resume tailoring, this is genuinely generated prose, so it cannot be constrained to selecting ids. The
guarantee is enforced two other ways instead:

1. **Restricted knowledge.** The model only ever sees the achievement bank, the profile and the voice notes, so
   there is nothing else available to assert.
2. **Post-hoc figure check.** Every number in the finished letter must already appear somewhere in the source
   material. This reuses the same reasoning as resume tailoring -- invented metrics are the most damaging and
   the cheapest to catch exactly -- and a letter that fails is refused rather than saved with a warning.

Cover letters are immutable and additive like resume versions: a re-run adds one, never overwrites.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.llm_provider import LLMProvider
from careeros.application.prompts.cover_letter_prompt import (
    COVER_LETTER_STRATEGY_VERSION,
    build_cover_letter_prompt,
)
from careeros.domain.candidate.application_answers import ApplicationAnswers
from careeros.domain.events import CoverLetterGenerated
from careeros.domain.repositories import (
    CandidateProfileRepository,
    CompanyRepository,
    JobRepository,
    ResumeRepository,
)
from careeros.domain.resume.achievement import AchievementBank
from careeros.domain.resume.resume_version import CoverLetter
from careeros.domain.resume.tailoring import FabricationError

logger = logging.getLogger(__name__)

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

# Numbers too generic to be a fabricated claim: years, small counts, and the candidate's own contact digits
# would otherwise trip the check on every letter.
_INNOCUOUS = re.compile(r"^(?:19|20)\d{2}$|^\d$")


class CoverLetterResponseError(ValueError):
    """Raised when the model's cover-letter response is unusable."""


@dataclass(frozen=True, slots=True)
class CoverLetterOutcome:
    cover_letter_id: str
    body: str
    achievements_referenced: list[str]
    gaps: list[str]


def _numbers_in(text: str) -> set[str]:
    return {
        match.group().replace(",", "")
        for match in _NUMBER.finditer(text or "")
        if not _INNOCUOUS.match(match.group().replace(",", ""))
    }


class CoverLetterService:
    def __init__(
        self,
        resume_repository: ResumeRepository,
        job_repository: JobRepository,
        company_repository: CompanyRepository,
        candidate_profile_repository: CandidateProfileRepository,
        achievement_bank: AchievementBank | None,
        answers: ApplicationAnswers,
        voice: str,
        llm_provider: LLMProvider,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._resume_repository = resume_repository
        self._job_repository = job_repository
        self._company_repository = company_repository
        self._candidate_profile_repository = candidate_profile_repository
        self._achievement_bank = achievement_bank
        self._answers = answers
        self._voice = voice
        self._llm_provider = llm_provider
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator

    async def generate_for_job(self, job_id: str, resume_version_id: str | None = None) -> CoverLetterOutcome:
        if self._achievement_bank is None:
            raise RuntimeError("No achievement bank loaded; a cover letter has nothing honest to draw on")

        job = await self._job_repository.get_by_id(job_id)
        if job is None:
            raise LookupError(f"Job {job_id} does not exist")

        profile = await self._candidate_profile_repository.get()
        if profile is None:
            raise RuntimeError("No candidate profile seeded; load config/profile.yaml first")

        company = await self._company_repository.get_by_id(job.company_id)
        company_name = company.name if company else "unknown"

        prompt = build_cover_letter_prompt(
            job, company_name, profile, self._answers, self._achievement_bank, self._voice
        )
        response = await self._llm_provider.complete(prompt)
        if response.parsed is None:
            raise CoverLetterResponseError(f"Model returned no parseable JSON for job {job_id}")

        body = str(response.parsed.get("body") or "").strip()
        if not body:
            raise CoverLetterResponseError("Model returned an empty cover letter")

        referenced = [str(item).strip() for item in (response.parsed.get("achievements_referenced") or [])]
        gaps = [str(item).strip() for item in (response.parsed.get("gaps") or []) if str(item).strip()]

        self._reject_invented_figures(body, profile, company_name)
        unknown = [ref for ref in referenced if ref and ref not in self._achievement_bank.ids]
        if unknown:
            raise FabricationError(f"Cover letter cites achievements not in the bank: {sorted(unknown)}")

        letter = CoverLetter(
            id=self._id_generator.new_id(),
            job_id=job_id,
            resume_version_id=resume_version_id or "",
            content=body,
            created_at=self._clock.now(),
        )
        await self._resume_repository.add_cover_letter(letter)
        await self._event_bus.publish(
            CoverLetterGenerated(
                cover_letter_id=letter.id, job_id=job_id, resume_version_id=letter.resume_version_id
            )
        )
        logger.info(
            "Wrote cover letter %s for job %s (strategy %s, %d gaps)",
            letter.id, job_id, COVER_LETTER_STRATEGY_VERSION, len(gaps),
        )
        return CoverLetterOutcome(
            cover_letter_id=letter.id, body=body, achievements_referenced=referenced, gaps=gaps
        )

    def _reject_invented_figures(self, body: str, profile, company_name: str) -> None:
        """Refuse a letter containing a figure absent from everything the model was allowed to see."""
        assert self._achievement_bank is not None
        source = " ".join(
            [
                company_name,
                profile.summary or "",
                profile.headline or "",
                str(profile.years_experience or ""),
                " ".join(profile.skills),
                " ".join(
                    bullet for achievement in self._achievement_bank.achievements for bullet in achievement.bullets
                ),
                " ".join(achievement.title for achievement in self._achievement_bank.achievements),
                self._answers.why_this_company_template,
                self._voice,
            ]
        )
        invented = _numbers_in(body) - _numbers_in(source)
        if invented:
            raise FabricationError(
                f"Cover letter introduces figures absent from your achievements: {sorted(invented)}"
            )
