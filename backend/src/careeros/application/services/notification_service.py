"""NotificationService -- batches routine events into a digest and sends urgent ones immediately.

No NotificationChannel adapter exists yet (see docs/architecture/decisions/0005-zero-paid-services-
constraint.md); this service's batching policy is implemented alongside the WhatsApp module in Phase 11.
"""
from __future__ import annotations

from typing import Any

from careeros.application.ports.clock import Clock
from careeros.application.ports.id_generator import IdGenerator
from careeros.application.ports.notification_channel import NotificationChannel


class NotificationService:
    def __init__(
        self,
        channel: NotificationChannel,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._channel = channel
        self._clock = clock
        self._id_generator = id_generator

    async def notify_immediate(self, template_id: str, payload: dict[str, Any]) -> None:
        """Send a high-urgency notification immediately, bypassing digest batching."""
        raise NotImplementedError("Notifications are implemented in Phase 11")

    async def enqueue_for_digest(self, template_id: str, payload: dict[str, Any]) -> None:
        """Queue a routine notification for the next periodic digest."""
        raise NotImplementedError("Notifications are implemented in Phase 11")
