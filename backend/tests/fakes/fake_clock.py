"""FakeClock -- a deterministic Clock for tests."""
from __future__ import annotations

from datetime import datetime


class FakeClock:
    def __init__(self, fixed_now: datetime) -> None:
        self._fixed_now = fixed_now

    def now(self) -> datetime:
        return self._fixed_now
