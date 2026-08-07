"""Tests for ScoringService: weighted combination, response validation, and batch resilience.

Deliberately no real model: `FakeLLMProvider` returns scripted JSON, so these assert CareerOS's own logic
rather than qwen3's judgment. The weighting tests matter most -- that arithmetic determines every ranking, and
unlike the model's output it must be exactly reproducible.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from careeros.application.ports.llm_provider import LLMResponse
from careeros.application.prompts.scoring_prompt import SCORING_STRATEGY_VERSION
from careeros.application.services.scoring_service import (
    DimensionWeights,
    ProfileNotConfiguredError,
    ScoreResponseError,
    ScoringService,
)
from careeros.domain.candidate.candidate_profile import CandidateProfile, RoleInterest
from careeros.domain.company.company import Company
from careeros.domain.events import JobScored
from careeros.domain.job.job import Job, JobSource, Location, RemoteType, SalaryRange
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_llm_provider import FakeLLMProvider
from tests.fakes.in_memory_company_repository import InMemoryCompanyRepository
from tests.fakes.in_memory_event_bus import InMemoryEventBus
from tests.fakes.in_memory_job_repository import InMemoryJobRepository
from tests.fakes.in_memory_score_repository import InMemoryScoreRepository
from tests.fakes.sequential_id_generator import SequentialIdGenerator

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)

EQUAL_WEIGHTS = DimensionWeights(
    resume_match=1.0,
    skill_area_fit=1.0,
    career_progression_fit=1.0,
    remote_fit=1.0,
    salary_fit=1.0,
    company_quality=1.0,
)

RESUME_ONLY_WEIGHTS = DimensionWeights(
    resume_match=1.0,
    skill_area_fit=0.0,
    career_progression_fit=0.0,
    remote_fit=0.0,
    salary_fit=0.0,
    company_quality=0.0,
)


def _model_response(**overrides) -> LLMResponse:
    parsed = {
        "resume_match": 80,
        "skill_area_fit": 80,
        "career_progression_fit": 80,
        "remote_fit": 80,
        "salary_fit": 80,
        "company_quality": 80,
        "narrative": "Strong overall fit.",
    }
    parsed.update(overrides)
    return LLMResponse(text="{}", parsed=parsed, model_used="qwen3:8b")


def _job(job_id: str = "job-1") -> Job:
    return Job(
        id=job_id,
        source=JobSource.GREENHOUSE,
        source_job_id=job_id,
        company_id="company-1",
        title="Senior AI Engineer",
        url="https://example.com/jobs/1",
        description="Build LLM systems in Python.",
        location=Location(city=None, country="US", remote_type=RemoteType.REMOTE),
        salary_range=SalaryRange(minimum=None, maximum=None, currency=None, period=None),
        skills=["python", "llm"],
        posting_date=None,
        discovered_at=NOW,
    )


def _profile() -> CandidateProfile:
    return CandidateProfile(
        id="candidate",
        headline="Software Engineer",
        summary="Builds backend and AI systems.",
        years_experience=2,
        skills=["python", "llm"],
        role_interests=[RoleInterest(title="AI Engineer", priority=5)],
    )


async def _build(
    response: LLMResponse | None = None,
    *,
    weights: DimensionWeights = EQUAL_WEIGHTS,
    with_profile: bool = True,
    jobs: list[Job] | None = None,
):
    scores = InMemoryScoreRepository()
    job_repository = InMemoryJobRepository(score_repository=scores)
    for job in jobs if jobs is not None else [_job()]:
        await job_repository.add(job)

    company_repository = InMemoryCompanyRepository()
    await company_repository.add(Company(id="company-1", name="Acme"))

    profile_repository = _StubProfileRepository(_profile() if with_profile else None)
    bus = InMemoryEventBus()
    llm = FakeLLMProvider(response or _model_response())

    service = ScoringService(
        job_repository=job_repository,
        score_repository=scores,
        company_repository=company_repository,
        candidate_profile_repository=profile_repository,
        llm_provider=llm,
        event_bus=bus,
        clock=FakeClock(NOW),
        id_generator=SequentialIdGenerator("score"),
        weights=weights,
    )
    return service, scores, bus, llm


class _StubProfileRepository:
    def __init__(self, profile: CandidateProfile | None) -> None:
        self._profile = profile

    async def get(self) -> CandidateProfile | None:
        return self._profile

    async def save(self, profile: CandidateProfile) -> None:
        self._profile = profile


class TestScoreJob:
    async def test_persists_a_score_and_publishes_job_scored(self) -> None:
        service, scores, bus, _ = await _build()

        score = await service.score_job("job-1")

        assert len(scores.scores) == 1
        assert score.value == 80
        assert score.scoring_strategy_version == SCORING_STRATEGY_VERSION
        assert score.model_used == "qwen3:8b"
        assert [type(event) for event in bus.published] == [JobScored]

    async def test_keeps_the_model_narrative_as_the_explanation(self) -> None:
        service, _, _, _ = await _build(_model_response(narrative="Remote and LLM-focused."))

        score = await service.score_job("job-1")

        assert score.explanation.narrative == "Remote and LLM-focused."

    async def test_sends_the_job_and_profile_to_the_model(self) -> None:
        service, _, _, llm = await _build()

        await service.score_job("job-1")

        prompt = llm.received_prompts[0]
        assert "Senior AI Engineer" in prompt.user_prompt
        assert "Acme" in prompt.user_prompt
        assert "AI Engineer (priority 5/5)" in prompt.user_prompt
        assert prompt.response_schema is not None, "structured output must be requested"

    async def test_missing_job_raises(self) -> None:
        service, _, _, _ = await _build()

        with pytest.raises(LookupError):
            await service.score_job("job-missing")

    async def test_missing_profile_raises_rather_than_scoring_blind(self) -> None:
        service, _, _, _ = await _build(with_profile=False)

        with pytest.raises(ProfileNotConfiguredError):
            await service.score_job("job-1")


class TestWeightedTotal:
    async def test_equal_weights_average_the_dimensions(self) -> None:
        service, _, _, _ = await _build(
            _model_response(resume_match=100, skill_area_fit=100, career_progression_fit=100,
                            remote_fit=0, salary_fit=0, company_quality=0)
        )

        score = await service.score_job("job-1")

        assert score.value == 50

    async def test_weights_actually_shift_the_result(self) -> None:
        response = _model_response(resume_match=100, skill_area_fit=0, career_progression_fit=0,
                                   remote_fit=0, salary_fit=0, company_quality=0)
        equal, _, _, _ = await _build(response, weights=EQUAL_WEIGHTS)
        resume_only, _, _, _ = await _build(response, weights=RESUME_ONLY_WEIGHTS)

        assert (await equal.score_job("job-1")).value == 17
        assert (await resume_only.score_job("job-1")).value == 100

    async def test_weights_are_normalized_so_they_need_not_sum_to_one(self) -> None:
        # Same relative emphasis, ten times the magnitude: the score must not change.
        tenfold = DimensionWeights(**{field: 10.0 for field in EQUAL_WEIGHTS.as_mapping()})
        service, _, _, _ = await _build(_model_response(resume_match=60, skill_area_fit=60,
                                                        career_progression_fit=60, remote_fit=60,
                                                        salary_fit=60, company_quality=60), weights=tenfold)

        assert (await service.score_job("job-1")).value == 60

    async def test_zero_weights_are_rejected(self) -> None:
        zeros = DimensionWeights(**{field: 0.0 for field in EQUAL_WEIGHTS.as_mapping()})
        service, _, _, _ = await _build(weights=zeros)

        with pytest.raises(ValueError, match="positive"):
            await service.score_job("job-1")


class TestResponseValidation:
    async def test_unparseable_response_raises(self) -> None:
        service, scores, _, _ = await _build(LLMResponse(text="not json", parsed=None, model_used="m"))

        with pytest.raises(ScoreResponseError):
            await service.score_job("job-1")
        assert scores.scores == [], "a garbage response must not produce a stored score"

    async def test_missing_dimension_raises(self) -> None:
        response = _model_response()
        del response.parsed["salary_fit"]
        service, _, _, _ = await _build(response)

        with pytest.raises(ScoreResponseError, match="salary_fit"):
            await service.score_job("job-1")

    @pytest.mark.parametrize("bad_value", [-1, 101, 1000])
    async def test_out_of_range_dimension_raises(self, bad_value: int) -> None:
        service, _, _, _ = await _build(_model_response(remote_fit=bad_value))

        with pytest.raises(ScoreResponseError, match="out of range"):
            await service.score_job("job-1")

    async def test_non_numeric_dimension_raises(self) -> None:
        service, _, _, _ = await _build(_model_response(remote_fit="very good"))

        with pytest.raises(ScoreResponseError, match="not numeric"):
            await service.score_job("job-1")

    async def test_empty_narrative_raises(self) -> None:
        service, _, _, _ = await _build(_model_response(narrative="   "))

        with pytest.raises(ScoreResponseError, match="narrative"):
            await service.score_job("job-1")


class TestScorePending:
    async def test_scores_the_backlog_and_reports_progress(self) -> None:
        jobs = [_job("job-1"), _job("job-2"), _job("job-3")]
        service, scores, _, _ = await _build(jobs=jobs)

        result = await service.score_pending(limit=2)

        assert (result.scored, result.failed, result.remaining) == (2, 0, 1)
        assert len(scores.scores) == 2

    async def test_a_failing_job_is_counted_and_does_not_abort_the_batch(self) -> None:
        jobs = [_job("job-1"), _job("job-2")]
        service, scores, _, llm = await _build(jobs=jobs)

        calls = {"n": 0}
        original = llm.complete

        async def flaky(prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("model unavailable")
            return await original(prompt)

        llm.complete = flaky

        result = await service.score_pending(limit=2)

        assert (result.scored, result.failed) == (1, 1)
        assert len(scores.scores) == 1

    async def test_missing_profile_fails_the_whole_batch_immediately(self) -> None:
        service, _, _, _ = await _build(with_profile=False, jobs=[_job("job-1"), _job("job-2")])

        with pytest.raises(ProfileNotConfiguredError):
            await service.score_pending(limit=2)

    async def test_empty_backlog_is_a_no_op(self) -> None:
        service, _, bus, _ = await _build(jobs=[])

        result = await service.score_pending(limit=10)

        assert (result.scored, result.failed, result.remaining) == (0, 0, 0)
        assert bus.published == []
