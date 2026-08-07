"""SequentialIdGenerator -- predictable ids ("id-1", "id-2", ...) so tests can assert on them."""
from __future__ import annotations

from itertools import count


class SequentialIdGenerator:
    def __init__(self, prefix: str = "id") -> None:
        self._prefix = prefix
        self._counter = count(1)

    def new_id(self) -> str:
        return f"{self._prefix}-{next(self._counter)}"
