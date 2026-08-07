"""InMemoryEventBus -- test fake that records every published event for assertions."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from careeros.domain.events import DomainEvent


class InMemoryEventBus:
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)

    def subscribe(self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], Awaitable[None]]) -> None:
        raise NotImplementedError("InMemoryEventBus only records published events for now")
