"""InProcessEventBus -- the phase-1 EventBus adapter: in-memory pub/sub within a single process.

Designed to be swapped for a Redis-backed bus later without changing publisher/subscriber code -- see
docs/architecture/decisions/0002-in-process-event-bus-with-swappable-backend.md.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from careeros.domain.events import DomainEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class InProcessEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._subscribers.get(type(event), [])
        if not handlers:
            logger.debug("No subscribers for event %s (%s)", event.event_type, event.event_id)
            return
        results = await asyncio.gather(*(handler(event) for handler in handlers), return_exceptions=True)
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error(
                    "Handler %s failed for event %s (%s): %s",
                    getattr(handler, "__qualname__", handler),
                    event.event_type,
                    event.event_id,
                    result,
                )
