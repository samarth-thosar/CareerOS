"""IdGenerator port -- kept as a seam purely for deterministic testing (see a fixed-sequence fake in tests)."""
from __future__ import annotations

from typing import Protocol


class IdGenerator(Protocol):
    def new_id(self) -> str: ...
