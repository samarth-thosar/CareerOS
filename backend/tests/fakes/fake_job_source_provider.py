"""FakeJobSourceProvider -- yields scripted postings so DiscoveryService is testable without network I/O."""
from __future__ import annotations

from collections.abc import AsyncIterator

from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria


class FakeJobSourceProvider:
    supports_auto_submit = False

    def __init__(self, name: str, postings: list[RawJobPosting]) -> None:
        self.name = name
        self._postings = postings
        self.received_criteria: list[SearchCriteria] = []

    async def search(self, criteria: SearchCriteria) -> AsyncIterator[RawJobPosting]:
        self.received_criteria.append(criteria)
        for posting in self._postings:
            yield posting
