"""ScoringService -- turns a discovered Job into a 0-100 Score with itemized reasoning.

The model rates six dimensions; this service computes the weighted total from configured weights (see
`careeros.application.prompts.scoring_prompt` for why the work is split that way).

Batching over a durable queue: on this hardware one scoring call takes roughly a minute, so a backlog of a
few hundred jobs is hours of inference. Rather than an in-memory work queue, "jobs with no Score row" *is*
the queue -- it survives restarts, cannot lose work, and lets a scheduled run chip away at the backlog a
bounded slice at a time. Concurrency stays low by default because a single local Ollama instance serializes
generation anyway, and parallel requests on a small GPU just thrash VRAM.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.llm_provider import LLMProvider
from careeros.application.prompts.scoring_prompt import (
    DIMENSIONS,
    SCORING_STRATEGY_VERSION,
    build_scoring_prompt,
)
from careeros.domain.events import JobScored
from careeros.domain.repositories import (
    CandidateProfileRepository,
    CompanyRepository,
    JobRepository,
    ScoreRepository,
)
from careeros.domain.scoring.score import Score, ScoreBreakdown

logger = logging.getLogger(__name__)


class ProfileNotConfiguredError(RuntimeError):
    """Raised when scoring is attempted before a CandidateProfile has been seeded."""


class ScoreResponseError(ValueError):
    """Raised when the model's response cannot be turned into a valid Score."""


@dataclass(frozen=True, slots=True)
class DimensionWeights:
    """Weights for combining dimension ratings into the final score.

    Passed in as a narrow value object rather than the whole Settings object, so this service never learns how
    configuration is loaded.
    """

    resume_match: float
    skill_area_fit: float
    career_progression_fit: float
    remote_fit: float
    salary_fit: float
    company_quality: float

    def as_mapping(self) -> dict[str, float]:
        return {dimension: getattr(self, dimension) for dimension in DIMENSIONS}

    def total(self) -> float:
        return sum(self.as_mapping().values())


@dataclass(frozen=True, slots=True)
class BatchResult:
    scored: int
    failed: int
    remaining: int


class ScoringService:
    def __init__(
        self,
        job_repository: JobRepository,
        score_repository: ScoreRepository,
        company_repository: CompanyRepository,
        candidate_profile_repository: CandidateProfileRepository,
        llm_provider: LLMProvider,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
        weights: DimensionWeights,
    ) -> None:
        self._job_repository = job_repository
        self._score_repository = score_repository
        self._company_repository = company_repository
        self._candidate_profile_repository = candidate_profile_repository
        self._llm_provider = llm_provider
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator
        self._weights = weights

    async def score_job(self, job_id: str) -> Score:
        """Score one job and publish JobScored.

        Raises rather than returning a fallback if the job, company or profile is missing, or if the model's
        response is unusable -- a made-up score would silently corrupt every decision downstream, whereas a
        failure leaves the job unscored and therefore retried by the next batch.
        """
        job = await self._job_repository.get_by_id(job_id)
        if job is None:
            raise LookupError(f"Job {job_id} does not exist")

        profile = await self._candidate_profile_repository.get()
        if profile is None:
            raise ProfileNotConfiguredError(
                "No candidate profile has been seeded; load config/profile.yaml before scoring"
            )

        company = await self._company_repository.get_by_id(job.company_id)
        company_name = company.name if company else "unknown"

        response = await self._llm_provider.complete(build_scoring_prompt(job, company_name, profile))
        if response.parsed is None:
            raise ScoreResponseError(f"Model returned no parseable JSON when scoring job {job_id}")

        breakdown = _breakdown_from(response.parsed)
        score = Score(
            id=self._id_generator.new_id(),
            job_id=job_id,
            value=self._weighted_total(breakdown),
            explanation=breakdown,
            scoring_strategy_version=SCORING_STRATEGY_VERSION,
            model_used=response.model_used,
            created_at=self._clock.now(),
        )
        await self._score_repository.add(score)
        await self._event_bus.publish(
            JobScored(
                job_id=job_id,
                score_id=score.id,
                value=score.value,
                scoring_strategy_version=SCORING_STRATEGY_VERSION,
            )
        )
        logger.info("Scored job %s at %d", job_id, score.value)
        return score

    async def score_pending(self, limit: int) -> BatchResult:
        """Score up to `limit` not-yet-scored jobs, oldest discovery first.

        One job failing does not abort the batch: it is counted and left unscored so the next run retries it.
        """
        pending = await self._job_repository.find_unscored(limit=limit)
        scored = failed = 0
        for job in pending:
            try:
                await self.score_job(job.id)
                scored += 1
            except ProfileNotConfiguredError:
                raise  # Nothing in the batch can succeed, so fail loudly instead of logging N times.
            except Exception:
                failed += 1
                logger.exception("Failed to score job %s", job.id)

        remaining = await self._job_repository.count_unscored()
        logger.info("Scoring batch complete: %d scored, %d failed, %d remaining", scored, failed, remaining)
        return BatchResult(scored=scored, failed=failed, remaining=remaining)

    def _weighted_total(self, breakdown: ScoreBreakdown) -> int:
        """Combine dimension ratings into 0-100 using the configured weights.

        Weights are normalized by their own sum, so an edited config that does not add up to 1.0 shifts
        emphasis without silently rescaling every score.
        """
        weights = self._weights.as_mapping()
        divisor = self._weights.total()
        if divisor <= 0:
            raise ValueError("Scoring weights must sum to a positive number")
        weighted = sum(getattr(breakdown, dimension) * weight for dimension, weight in weights.items())
        return max(0, min(100, round(weighted / divisor)))


def _breakdown_from(parsed: dict) -> ScoreBreakdown:
    """Validate the model's JSON into a ScoreBreakdown, rejecting anything out of range or missing."""
    values: dict[str, float] = {}
    for dimension in DIMENSIONS:
        if dimension not in parsed:
            raise ScoreResponseError(f"Model response is missing dimension {dimension!r}")
        try:
            value = float(parsed[dimension])
        except (TypeError, ValueError) as error:
            raise ScoreResponseError(f"Dimension {dimension!r} is not numeric: {parsed[dimension]!r}") from error
        if not 0 <= value <= 100:
            raise ScoreResponseError(f"Dimension {dimension!r} out of range 0-100: {value}")
        values[dimension] = value

    narrative = str(parsed.get("narrative") or "").strip()
    if not narrative:
        raise ScoreResponseError("Model response has an empty narrative")

    return ScoreBreakdown(**values, narrative=narrative)
