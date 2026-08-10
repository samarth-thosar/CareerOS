"""The composition root: the only module that sees domain, application, and infrastructure at once.

Two things make this file the map of the system:

1. `build_services` -- every service constructed explicitly, dependencies passed in, no framework magic.
2. `register_event_handlers` -- the subscription table, as one flat greppable list of
   `EventType -> service method`.

Unit-of-work rule: each event handler and each scheduled job opens its *own* session and builds its own
services (`in_session`). Services publish into a per-unit-of-work `DeferredEventBus`, which is drained onto
the process-wide bus only after that transaction commits -- so no subscriber ever acts on a fact a rollback
would have erased, and no subscriber's write contends with the publisher's still-open transaction. Handlers
therefore commit independently of whoever published the event, which is exactly how they will behave once the
bus is Redis/Celery-backed. The cost is that a publisher and its handlers are not one atomic transaction,
which is why handlers are written to be idempotent.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.job_source_provider import JobSourceProvider, SearchCriteria
from careeros.application.services.application_submission_service import ApplicationSubmissionService
from careeros.application.services.application_tracker_service import ApplicationTrackerService
from careeros.application.services.candidate_profile_service import CandidateProfileService
from careeros.application.services.command_dispatcher import CommandDispatcher
from careeros.application.services.company_intelligence_service import CompanyIntelligenceService
from careeros.application.services.company_resolver import CompanyResolver
from careeros.application.services.cover_letter_service import CoverLetterService
from careeros.application.services.discovery_service import DiscoveryService
from careeros.application.services.memory_service import MemoryService
from careeros.application.services.resume_manager_service import ResumeManagerService
from careeros.application.services.scoring_service import DimensionWeights, ScoringService
from careeros.domain.candidate.application_answers import ApplicationAnswers
from careeros.domain.candidate.candidate_profile import CandidateProfile
from careeros.domain.job.location_eligibility import EligibilityRules
from careeros.domain.events import (
    CoverLetterGenerated,
    JobDiscovered,
    JobScored,
    ResumeGenerated,
)
from careeros.infrastructure.config.answers_loader import load_answers, load_voice
from careeros.infrastructure.config.profile_loader import load_profile
from careeros.infrastructure.config.settings import Settings, load_settings
from careeros.infrastructure.events.deferred_event_bus import DeferredEventBus
from careeros.infrastructure.events.in_process_event_bus import InProcessEventBus
from careeros.infrastructure.job_sources.greenhouse_provider import GreenhouseProvider
from careeros.infrastructure.llm.ollama_provider import OllamaProvider
from careeros.infrastructure.persistence.db import create_engine, create_session_factory, session_scope
from careeros.domain.resume.achievement import AchievementBank
from careeros.infrastructure.resume.achievement_loader import load_achievement_bank
from careeros.infrastructure.resume.artifact_store import ArtifactStore as LocalArtifactStore
from careeros.infrastructure.resume.latex_renderer import LatexRenderer
from careeros.infrastructure.resume.local_tex_resume_source import LocalTexResumeSource
from careeros.infrastructure.resume.tex_assembler import TexAssembler
from careeros.infrastructure.persistence.repositories import (
    SqlAlchemyApplicationRepository,
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyCompanyRepository,
    SqlAlchemyJobRepository,
    SqlAlchemyResumeRepository,
    SqlAlchemyScoreRepository,
)
from careeros.infrastructure.scheduler.apscheduler_adapter import APSchedulerAdapter

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UuidGenerator:
    def new_id(self) -> str:
        return str(uuid.uuid4())


@dataclass(slots=True)
class Repositories:
    """A per-session bundle of repositories, all sharing one unit of work."""

    jobs: SqlAlchemyJobRepository
    companies: SqlAlchemyCompanyRepository
    applications: SqlAlchemyApplicationRepository
    scores: SqlAlchemyScoreRepository
    resumes: SqlAlchemyResumeRepository
    candidate_profile: SqlAlchemyCandidateProfileRepository


def build_repositories(session: AsyncSession) -> Repositories:
    return Repositories(
        jobs=SqlAlchemyJobRepository(session),
        companies=SqlAlchemyCompanyRepository(session),
        applications=SqlAlchemyApplicationRepository(session),
        scores=SqlAlchemyScoreRepository(session),
        resumes=SqlAlchemyResumeRepository(session),
        candidate_profile=SqlAlchemyCandidateProfileRepository(session),
    )


@dataclass(slots=True)
class Container:
    """The process-wide singletons built once at startup by `build_container()`."""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    clock: Clock
    id_generator: IdGenerator
    event_bus: InProcessEventBus
    llm_provider: OllamaProvider
    scheduler: APSchedulerAdapter
    job_source_providers: list[JobSourceProvider]
    resume_source: LocalTexResumeSource
    resume_renderer: LatexRenderer
    artifact_store: LocalArtifactStore
    # Loaded once at startup: the bank is a file the user edits between runs, not per-request state. A reload
    # endpoint replaces it in place rather than each request re-reading YAML from disk.
    achievement_bank: AchievementBank | None
    # Answers and voice are files the user edits between runs; reload endpoints replace them in place rather
    # than each request re-reading from disk.
    answers: ApplicationAnswers
    voice: str


def search_criteria_from(settings: Settings) -> SearchCriteria:
    """Translate discovery config into the domain-facing criteria object.

    Single source of this mapping -- the scheduler, the startup cycle, and the manual trigger endpoint all
    call here so they cannot drift apart.
    """
    discovery = settings.discovery
    return SearchCriteria(
        title_keywords=list(discovery.title_keywords),
        keywords=list(discovery.keywords),
        remote_only=discovery.remote_only,
        eligibility=(
            EligibilityRules.from_locations(list(discovery.eligible_locations))
            if discovery.eligible_locations
            else None
        ),
    )


def build_job_source_providers(settings: Settings) -> list[JobSourceProvider]:
    """Instantiate only the sources switched on in config, so a disabled source costs nothing at runtime."""
    providers: list[JobSourceProvider] = []
    greenhouse = settings.job_sources.greenhouse
    if greenhouse.enabled and greenhouse.board_tokens:
        providers.append(GreenhouseProvider(board_tokens=list(greenhouse.board_tokens)))
    return providers


def build_container() -> Container:
    settings = load_settings()
    engine = create_engine(settings.database_url)

    return Container(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
        event_bus=InProcessEventBus(),
        llm_provider=OllamaProvider(
            base_url=settings.llm.base_url,
            model=settings.llm.model,
            timeout_seconds=settings.llm.timeout_seconds,
            keep_alive=settings.llm.keep_alive,
            max_output_tokens=settings.llm.max_output_tokens,
            disable_thinking=settings.llm.disable_thinking,
        ),
        scheduler=APSchedulerAdapter(),
        job_source_providers=build_job_source_providers(settings),
        resume_source=LocalTexResumeSource(),
        resume_renderer=LatexRenderer(engine=settings.resume.latex_engine or None),
        artifact_store=LocalArtifactStore(),
        achievement_bank=_load_bank_or_warn(),
        answers=load_answers(),
        voice=load_voice(),
    )


def _load_bank_or_warn() -> AchievementBank | None:
    """Load the achievement bank, tolerating its absence.

    A missing or invalid bank disables tailoring but must not stop the app booting -- discovery, scoring and the
    dashboard are all still useful, and the error is far easier to act on from a running system.
    """
    try:
        return load_achievement_bank()
    except Exception:
        logger.exception("Could not load the achievement bank; resume tailoring will be unavailable")
        return None


@dataclass(slots=True)
class Services:
    """Use-case services for a single unit of work, built against one session's repositories.

    `resume_manager` is None when the achievement bank could not be loaded, since tailoring has nothing honest
    to draw from without it. `NotificationService` is still absent pending its adapter; see
    docs/architecture/decisions/0005-zero-paid-services-constraint.md.
    """

    discovery: DiscoveryService
    scoring: ScoringService
    application_tracker: ApplicationTrackerService
    submission: ApplicationSubmissionService
    candidate_profile: CandidateProfileService
    company_intelligence: CompanyIntelligenceService
    company_resolver: CompanyResolver
    resume_manager: ResumeManagerService | None
    cover_letter: CoverLetterService
    memory: MemoryService
    command_dispatcher: CommandDispatcher


def build_services(container: Container, repos: Repositories, event_bus: EventBus) -> Services:
    """Construct the services for one unit of work.

    `event_bus` is passed in rather than taken from the container because within a transaction it must be the
    per-unit-of-work `DeferredEventBus`, not the process-wide bus -- see this module's docstring.
    """
    company_resolver = CompanyResolver(
        company_repository=repos.companies, id_generator=container.id_generator
    )
    return Services(
        discovery=DiscoveryService(
            providers=container.job_source_providers,
            job_repository=repos.jobs,
            company_resolver=company_resolver,
            event_bus=event_bus,
            clock=container.clock,
            id_generator=container.id_generator,
        ),
        scoring=ScoringService(
            job_repository=repos.jobs,
            score_repository=repos.scores,
            company_repository=repos.companies,
            candidate_profile_repository=repos.candidate_profile,
            llm_provider=container.llm_provider,
            event_bus=event_bus,
            clock=container.clock,
            id_generator=container.id_generator,
            weights=DimensionWeights(**container.settings.scoring_weights.model_dump()),
        ),
        application_tracker=ApplicationTrackerService(
            application_repository=repos.applications,
            event_bus=event_bus,
            clock=container.clock,
            id_generator=container.id_generator,
            auto_interested_threshold=container.settings.tracker.auto_interested_threshold,
        ),
        submission=ApplicationSubmissionService(
            application_repository=repos.applications,
            job_repository=repos.jobs,
            resume_repository=repos.resumes,
            providers=container.job_source_providers,
            answers=container.answers,
            event_bus=event_bus,
            clock=container.clock,
        ),
        candidate_profile=CandidateProfileService(
            candidate_profile_repository=repos.candidate_profile,
        ),
        company_intelligence=CompanyIntelligenceService(
            company_repository=repos.companies,
            clock=container.clock,
            id_generator=container.id_generator,
        ),
        company_resolver=company_resolver,
        resume_manager=(
            ResumeManagerService(
                resume_repository=repos.resumes,
                job_repository=repos.jobs,
                company_repository=repos.companies,
                candidate_profile_repository=repos.candidate_profile,
                resume_source=container.resume_source,
                achievement_bank=container.achievement_bank,
                renderer=container.resume_renderer,
                artifact_store=container.artifact_store,
                assembler=TexAssembler(),
                llm_provider=container.llm_provider,
                event_bus=event_bus,
                clock=container.clock,
                id_generator=container.id_generator,
            )
            if container.achievement_bank is not None
            else None
        ),
        cover_letter=CoverLetterService(
            resume_repository=repos.resumes,
            job_repository=repos.jobs,
            company_repository=repos.companies,
            candidate_profile_repository=repos.candidate_profile,
            achievement_bank=container.achievement_bank,
            answers=container.answers,
            voice=container.voice,
            llm_provider=container.llm_provider,
            event_bus=event_bus,
            clock=container.clock,
            id_generator=container.id_generator,
        ),
        memory=MemoryService(
            application_repository=repos.applications,
            score_repository=repos.scores,
        ),
        command_dispatcher=CommandDispatcher(),
    )


async def in_session(container: Container, work: Callable[[Services], Awaitable[T]]) -> T:
    """Run `work` in its own transaction, then release its events.

    Events raised by `work` are held in a `DeferredEventBus` and only dispatched once the transaction has
    committed. If `work` raises, the transaction rolls back and the collected events are discarded with it --
    subscribers never hear about work that did not happen.
    """
    outbox = DeferredEventBus()
    async with session_scope(container.session_factory) as session:
        services = build_services(container, build_repositories(session), outbox)
        result = await work(services)

    await outbox.dispatch_to(container.event_bus)
    return result


def register_event_handlers(container: Container) -> None:
    """The subscription table. One line per (event, reacting service method).

    Each handler runs in its own transaction via `in_session`, so adding a subscriber never widens an
    existing publisher's transaction.
    """

    async def on_job_discovered(event: JobDiscovered) -> None:
        await in_session(container, lambda s: s.application_tracker.track_discovered_job(event.job_id))

    async def on_job_scored(event: JobScored) -> None:
        await in_session(container, lambda s: s.application_tracker.apply_score(event.job_id, event.value))

    async def on_resume_generated(event: ResumeGenerated) -> None:
        await in_session(
            container,
            lambda s: s.application_tracker.attach_resume(event.job_id, event.resume_version_id),
        )

    async def on_cover_letter_generated(event: CoverLetterGenerated) -> None:
        await in_session(
            container,
            lambda s: s.application_tracker.record_cover_letter(event.job_id, event.cover_letter_id),
        )

    container.event_bus.subscribe(JobDiscovered, on_job_discovered)
    container.event_bus.subscribe(JobScored, on_job_scored)
    container.event_bus.subscribe(ResumeGenerated, on_resume_generated)
    container.event_bus.subscribe(CoverLetterGenerated, on_cover_letter_generated)


def register_scheduled_jobs(container: Container) -> None:
    """Periodic work, registered through SchedulerPort so the Celery swap stays a wiring-only change."""
    if not container.settings.scheduler.enabled:
        logger.info("Scheduler disabled by config; no background discovery or scoring will run")
        return

    criteria = search_criteria_from(container.settings)

    for provider in container.job_source_providers:
        provider_name = provider.name

        def make_cycle(name: str) -> Callable[[], Awaitable[None]]:
            async def run_cycle() -> None:
                await in_session(container, lambda s: s.discovery.run_cycle(name, criteria))

            return run_cycle

        container.scheduler.schedule_interval(
            f"discovery:{provider_name}",
            make_cycle(provider_name),
            container.settings.discovery.interval_seconds,
        )

    # Drains the scoring backlog a bounded slice at a time. Deliberately not driven by JobDiscovered: a single
    # discovery run can add hundreds of jobs, and at ~1 minute of local inference each, reacting per-event
    # would fan out into an unbounded pile of concurrent LLM calls.
    async def score_batch() -> None:
        await in_session(
            container, lambda s: s.scoring.score_pending(container.settings.scoring.batch_size)
        )

    container.scheduler.schedule_interval(
        "scoring:pending", score_batch, container.settings.scoring.interval_seconds
    )


async def seed_candidate_profile(container: Container) -> CandidateProfile:
    """Load config/profile.yaml into the database, replacing the single profile row."""
    profile = load_profile()
    return await in_session(container, lambda s: s.candidate_profile.replace(profile))
