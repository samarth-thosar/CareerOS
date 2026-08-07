"""Clock port -- kept as a seam purely for deterministic testing (see FakeClock in tests/fakes)."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
