"""CommandDispatcher -- routes InboundCommandReceived events to the appropriate application service.

Implemented alongside the WhatsApp module in Phase 11.
"""
from __future__ import annotations

from typing import Any

from careeros.domain.notification.notification_message import CommandIntent


class CommandDispatcher:
    def __init__(self) -> None:
        pass

    async def dispatch(self, intent: CommandIntent, parameters: dict[str, Any]) -> None:
        """Route a parsed inbound command (e.g. ApplyApproved, ShowSummary) to its handling service."""
        raise NotImplementedError("Command dispatch is implemented in Phase 11")
