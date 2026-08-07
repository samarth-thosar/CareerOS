"""EventBus port -- the seam between in-process pub/sub (phase 1) and a future Redis/Celery-backed bus.

See docs/architecture/decisions/0002-in-process-event-bus-with-swappable-backend.md.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from careeros.domain.events import DomainEvent

EventT = TypeVar("EventT", bound=DomainEvent)
EventHandler = Callable[[EventT], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, event_type: type[EventT], handler: EventHandler) -> None: ...
