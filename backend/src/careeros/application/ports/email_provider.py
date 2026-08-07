"""EmailProvider port -- interface only in this phase (Gmail adapter lands with the Email module phase).

`send_draft` must only ever be called after an explicit human approval gate -- see `EmailMessage.sent_at` in
docs/architecture/01-domain-model.md for how that invariant is represented in the domain.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(slots=True)
class RawEmailMessage:
    gmail_message_id: str
    thread_id: str
    from_address: str
    subject: str
    body: str
    received_at: datetime


class EmailProvider(Protocol):
    async def fetch_new_messages(self, since: datetime) -> list[RawEmailMessage]: ...
    async def create_draft_reply(self, thread_id: str, body: str) -> str: ...
    async def send_draft(self, draft_id: str) -> None: ...
