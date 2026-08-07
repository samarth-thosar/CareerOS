"""EmailMessage -- domain shape only.

No EmailProvider adapter exists yet in this phase; see docs/architecture/decisions/0005-zero-paid-services-
constraint.md and the Phase 11 roadmap note in 02-ports-and-interfaces.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EmailClassification(StrEnum):
    RECRUITER_OUTREACH = "recruiter_outreach"
    INTERVIEW_INVITE = "interview_invite"
    ASSESSMENT_INVITE = "assessment_invite"
    OFFER_LETTER = "offer_letter"
    REJECTION = "rejection"
    OTHER = "other"


@dataclass(slots=True)
class EmailMessage:
    """A classified inbound email.

    `sent_at` stays None until an explicit approval gate passes for any drafted reply -- this field's
    existence is how "never auto-send" is structurally enforced, not just a policy convention.
    """

    id: str
    gmail_message_id: str
    thread_id: str
    from_address: str
    subject: str
    received_at: datetime
    classification: EmailClassification
    confidence: float
    linked_company_id: str | None = None
    linked_application_id: str | None = None
    draft_reply_id: str | None = None
    requires_approval: bool = True
    sent_at: datetime | None = None
