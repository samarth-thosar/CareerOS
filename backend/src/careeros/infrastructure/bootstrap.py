"""The composition root: the only module that sees domain, application, and infrastructure at once.

Builds settings, the async engine, the event bus, and every service with its dependencies passed via
constructor injection. Event subscriptions and scheduled jobs are meant to be registered here as an
explicit, flat, greppable table -- see docs/architecture/decisions/0003-manual-composition-root-for-
dependency-injection.md -- but the table is empty in this phase, since no service yet has a real
event-reacting method to subscribe (they raise `NotImplementedError` until their owning phase lands).

Services whose ports have no adapter yet (`NotificationChannel`, `EmailProvider`, `ResumeSource`) are not
constructed in this phase -- see docs/architecture/decisions/0005-zero-paid-services-constraint.md and each
service's own docstring for which phase adds them.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from careeros.application.ports.clock import Clock
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.services.application_tracker_service import ApplicationTrackerService
from careeros.application.services.command_dispatcher import CommandDispatcher
from careeros.application.services.company_intelligence_service import CompanyIntelligenceService
from careeros.application.services.cover_letter_service import CoverLetterService
from careeros.application.services.discovery_service import DiscoveryService
from careeros.application.services.memory_service import MemoryService
from careeros.application.services.scoring_service import ScoringService
from careeros.infrastructure.config.settings import Settings, load_settings
from careeros.infrastructure.events.in_process_event_bus import InProcessEventBus
from careeros.infrastructure.llm.ollama_provider import OllamaProvider
from careeros.infrastructure.persistence.db import create_engine, create_session_factory
from careeros.infrastructure.persistence.repositories import (
    SqlAlchemyApplicationRepository,
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyCompanyRepository,
    SqlAlchemyJobRepository,
    SqlAlchemyResumeRepository,
    SqlAlchemyScoreRepository,
)
from careeros.infrastructure.scheduler.apscheduler_adapter import APSchedulerAdapter


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


def build_container() -> Container:
    settings = load_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    return Container(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        clock=SystemClock(),
        id_generator=UuidGenerator(),
        event_bus=InProcessEventBus(),
        llm_provider=OllamaProvider(base_url=settings.llm.base_url, model=settings.llm.model),
        scheduler=APSchedulerAdapter(),
    )


@dataclass(slots=True)
class Services:
    """Use-case services for a single unit of work, built against one session's repositories.

    Only services whose ports all have a phase-1 adapter are constructed here. `ResumeManagerService`,
    `NotificationService`, and a populated `DiscoveryService.providers` list are wired in once Phase 7, 11,
    and 4 respectively add their adapters.
    """

    discovery: DiscoveryService
    scoring: ScoringService
    application_tracker: ApplicationTrackerService
    company_intelligence: CompanyIntelligenceService
    cover_letter: CoverLetterService
    memory: MemoryService
    command_dispatcher: CommandDispatcher


def build_services(container: Container, repos: Repositories) -> Services:
    return Services(
        discovery=DiscoveryService(
            providers=[],
            job_repository=repos.jobs,
            company_repository=repos.companies,
            event_bus=container.event_bus,
            clock=container.clock,
            id_generator=container.id_generator,
        ),
        scoring=ScoringService(
            job_repository=repos.jobs,
            score_repository=repos.scores,
            candidate_profile_repository=repos.candidate_profile,
            llm_provider=container.llm_provider,
            event_bus=container.event_bus,
            clock=container.clock,
            id_generator=container.id_generator,
        ),
        application_tracker=ApplicationTrackerService(
            application_repository=repos.applications,
            event_bus=container.event_bus,
            clock=container.clock,
            id_generator=container.id_generator,
        ),
        company_intelligence=CompanyIntelligenceService(
            company_repository=repos.companies,
            clock=container.clock,
            id_generator=container.id_generator,
        ),
        cover_letter=CoverLetterService(
            resume_repository=repos.resumes,
            llm_provider=container.llm_provider,
            event_bus=container.event_bus,
            clock=container.clock,
            id_generator=container.id_generator,
        ),
        memory=MemoryService(
            application_repository=repos.applications,
            score_repository=repos.scores,
        ),
        command_dispatcher=CommandDispatcher(),
    )
