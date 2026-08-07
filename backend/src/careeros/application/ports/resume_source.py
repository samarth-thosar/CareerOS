"""ResumeSource port -- interface only in this phase (Overleaf adapter lands with the Resume Manager phase)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class MasterResumeSnapshot:
    version_ref: str
    content: str


class ResumeSource(Protocol):
    async def fetch_master(self) -> MasterResumeSnapshot: ...
