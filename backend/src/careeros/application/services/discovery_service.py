"""DiscoveryService -- runs one discovery cycle per job source.

Provider-agnostic by design: providers hand over already-normalized `RawJobPosting`s, so this service only
does the parts that are the same for every source -- de-duplicate, resolve the company, persist, announce.

Pipeline position: step 1 of docs/architecture/03-event-catalog-and-pipeline.md. Publishing `JobDiscovered`
is what causes an Application to be created and the job to be scored; this service knows nothing about
either of those consumers.
"""
from __future__ import annotations

import logging

from careeros.application.ports.clock import Clock
from careeros.application.ports.event_bus import EventBus
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.job_source_provider import JobSourceProvider, RawJobPosting, SearchCriteria
from careeros.application.services.company_resolver import CompanyResolver
from careeros.domain.events import JobDiscovered
from careeros.domain.job.job import Job, JobSource
from careeros.domain.repositories import JobRepository

logger = logging.getLogger(__name__)


class UnknownProviderError(LookupError):
    """Raised when a cycle is requested for a provider name that isn't registered."""


class DiscoveryService:
    def __init__(
        self,
        providers: list[JobSourceProvider],
        job_repository: JobRepository,
        company_resolver: CompanyResolver,
        event_bus: EventBus,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self._job_repository = job_repository
        self._company_resolver = company_resolver
        self._event_bus = event_bus
        self._clock = clock
        self._id_generator = id_generator

    async def run_cycle(self, provider_name: str, criteria: SearchCriteria) -> list[str]:
        """Search one provider and persist everything not seen before.

        Returns the ids of newly created Jobs. Re-discovering a posting is a silent no-op, which is what
        makes it safe to run this on a short timer.
        """
        provider = self._providers.get(provider_name)
        if provider is None:
            raise UnknownProviderError(f"No job source provider registered under {provider_name!r}")

        source = JobSource(provider_name)
        discovered_ids: list[str] = []
        seen_this_cycle: set[str] = set()

        async for posting in provider.search(criteria):
            # A single cycle can legitimately surface the same posting twice (e.g. a company listed under two
            # board tokens); guard in-memory as well as against the database.
            if posting.source_job_id in seen_this_cycle:
                continue
            seen_this_cycle.add(posting.source_job_id)

            if await self._job_repository.find_by_source(source, posting.source_job_id) is not None:
                continue

            job = await self._persist(posting, source)
            discovered_ids.append(job.id)
            await self._event_bus.publish(
                JobDiscovered(job_id=job.id, company_id=job.company_id, source=source.value, url=job.url)
            )

        logger.info("Discovery cycle for %s found %d new jobs", provider_name, len(discovered_ids))
        return discovered_ids

    async def add_posting(self, posting: RawJobPosting, source: JobSource) -> tuple[Job, bool]:
        """Persist a single posting produced outside a discovery cycle, e.g. one the candidate pasted in.

        Returns the job and whether it is new, so the caller can distinguish "added" from "you already had this"
        instead of silently doing nothing. Deliberately skips the eligibility filter that `run_cycle` applies:
        that filter exists to stop automated discovery wasting scoring time on unreachable roles, whereas a
        deliberate paste is an explicit choice and overriding it would be presumptuous.
        """
        existing = await self._job_repository.find_by_source(source, posting.source_job_id)
        if existing is not None:
            logger.info("Posting already tracked: %s", posting.source_job_id)
            return existing, False

        job = await self._persist(posting, source)
        await self._event_bus.publish(
            JobDiscovered(job_id=job.id, company_id=job.company_id, source=source.value, url=job.url)
        )
        logger.info("Added posting %s (%s at %s)", job.id, posting.title, posting.company_name)
        return job, True

    async def _persist(self, posting: RawJobPosting, source: JobSource) -> Job:
        company = await self._company_resolver.resolve(posting.company_name)
        job = Job(
            id=self._id_generator.new_id(),
            source=source,
            source_job_id=posting.source_job_id,
            company_id=company.id,
            title=posting.title,
            url=posting.url,
            description=posting.description,
            location=posting.location,
            salary_range=posting.salary_range,
            skills=posting.skills,
            posting_date=posting.posting_date,
            discovered_at=self._clock.now(),
            raw_payload=posting.raw_payload,
        )
        await self._job_repository.add(job)
        return job
