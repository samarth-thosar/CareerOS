"""NotificationChannel port -- interface only in this phase.

No adapter is implemented yet; the WhatsApp adapter choice (Meta Cloud API free tier vs. a self-hosted
bridge) is made explicitly with the user at Phase 11. See
docs/architecture/decisions/0005-zero-paid-services-constraint.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from careeros.domain.notification.notification_message import DeliveryStatus, NotificationMessage


@dataclass(slots=True)
class DeliveryResult:
    status: DeliveryStatus
    provider_message_id: str | None = None
    error: str | None = None


class NotificationChannel(Protocol):
    async def send(self, message: NotificationMessage) -> DeliveryResult: ...
