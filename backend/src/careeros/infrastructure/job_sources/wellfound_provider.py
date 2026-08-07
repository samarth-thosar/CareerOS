"""WellfoundProvider -- Playwright-based JobSourceProvider for Wellfound.

Implemented in Phase 4 (Job Discovery). The class exists now so `DiscoveryService.providers` has a real
type to grow into once scraping is built; `search()` raises until then.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from careeros.application.ports.job_source_provider import RawJobPosting, SearchCriteria


class WellfoundProvider:
    name = "wellfound"
    supports_auto_submit = False

    async def search(self, criteria: SearchCriteria) -> AsyncIterator[RawJobPosting]:
        raise NotImplementedError("Wellfound scraping is implemented in Phase 4")
        yield  # pragma: no cover -- keeps this an async generator, matching the port's shape
