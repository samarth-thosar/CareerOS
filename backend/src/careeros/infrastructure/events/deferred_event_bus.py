"""DeferredEventBus -- an in-memory outbox that holds events until their transaction commits.

Services publish here rather than straight onto the real bus. `bootstrap.in_session` drains it *after* the
unit of work commits, which buys two things:

1. **Correctness.** An event is a statement that something happened. Publishing mid-transaction can announce
   a job that a later rollback erases, leaving subscribers acting on a fact that was never true.
2. **No self-inflicted write contention.** Subscribers run in their own transaction (see bootstrap). If the
   publisher were still holding a write lock, the subscriber's insert would block on it -- on SQLite that is
   an immediate "database is locked" failure rather than a wait.

Same interface as the real bus, so services cannot tell the difference and need no transaction awareness.
When the bus becomes Redis/Celery-backed, this class is exactly where a durable outbox table would slot in.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from careeros.application.ports.event_bus import EventBus
from careeros.domain.events import DomainEvent


class DeferredEventBus:
    def __init__(self) -> None:
        self._pending: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self._pending.append(event)

    def subscribe(self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], Awaitable[None]]) -> None:
        raise NotImplementedError(
            "DeferredEventBus is write-only; subscribe on the process-wide bus in bootstrap instead"
        )

    @property
    def pending(self) -> list[DomainEvent]:
        return list(self._pending)

    async def dispatch_to(self, bus: EventBus) -> None:
        """Hand every collected event to the real bus, then clear. Called only after a successful commit."""
        events, self._pending = self._pending, []
        for event in events:
            await bus.publish(event)
