"""Tests for DeferredEventBus and the transactional guarantee it provides.

The rollback case is the one that matters: a failed unit of work must not leave subscribers believing
something happened. That is verified against the real `in_session` in
tests/integration/test_event_dispatch.py; here we pin the bus's own behavior.
"""
from __future__ import annotations

import pytest

from careeros.domain.events import JobDiscovered
from careeros.infrastructure.events.deferred_event_bus import DeferredEventBus
from tests.fakes.in_memory_event_bus import InMemoryEventBus


def _event(job_id: str) -> JobDiscovered:
    return JobDiscovered(job_id=job_id, company_id="c-1", source="greenhouse", url="https://example.com")


async def test_publish_holds_events_instead_of_forwarding_them() -> None:
    outbox = DeferredEventBus()
    downstream = InMemoryEventBus()

    await outbox.publish(_event("job-1"))

    assert downstream.published == [], "nothing may reach the real bus before dispatch"
    assert len(outbox.pending) == 1


async def test_dispatch_forwards_in_publication_order_then_clears() -> None:
    outbox = DeferredEventBus()
    downstream = InMemoryEventBus()
    await outbox.publish(_event("job-1"))
    await outbox.publish(_event("job-2"))

    await outbox.dispatch_to(downstream)

    assert [event.job_id for event in downstream.published] == ["job-1", "job-2"]
    assert outbox.pending == []


async def test_second_dispatch_does_not_resend() -> None:
    outbox = DeferredEventBus()
    downstream = InMemoryEventBus()
    await outbox.publish(_event("job-1"))

    await outbox.dispatch_to(downstream)
    await outbox.dispatch_to(downstream)

    assert len(downstream.published) == 1


async def test_undispatched_events_are_simply_dropped() -> None:
    # This is what a rolled-back transaction relies on: the outbox is discarded, never dispatched.
    outbox = DeferredEventBus()
    downstream = InMemoryEventBus()

    await outbox.publish(_event("job-1"))
    del outbox

    assert downstream.published == []


async def test_subscribing_on_the_outbox_is_rejected() -> None:
    with pytest.raises(NotImplementedError):
        DeferredEventBus().subscribe(JobDiscovered, lambda event: None)
