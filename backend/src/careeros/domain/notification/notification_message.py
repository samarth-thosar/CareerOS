"""NotificationMessage (outbound) and InboundCommand -- channel-agnostic shapes.

No NotificationChannel adapter exists yet; see docs/architecture/decisions/0005-zero-paid-services-
constraint.md for why WhatsApp is deferred to Phase 11.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NotificationUrgency(StrEnum):
    DIGEST = "digest"
    IMMEDIATE = "immediate"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass(slots=True)
class NotificationMessage:
    id: str
    channel: str
    template_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    urgency: NotificationUrgency = NotificationUrgency.DIGEST
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING


class CommandIntent(StrEnum):
    APPLY_APPROVED = "apply_approved"
    SHOW_INTERVIEWS = "show_interviews"
    SHOW_SUMMARY = "show_summary"
    PAUSE_APPLICATIONS = "pause_applications"
    RESUME_APPLICATIONS = "resume_applications"
    GENERATE_DAILY_REPORT = "generate_daily_report"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class InboundCommand:
    id: str
    channel: str
    raw_text: str
    parsed_intent: CommandIntent
    parameters: dict[str, Any] = field(default_factory=dict)
