"""Job list filters.

A value object rather than a long parameter list, so the API layer, the read model and any future caller all
agree on what a filter set is, and adding a dimension does not change three signatures.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobFilters:
    """Every field is optional; an unset field is simply not applied.

    `min_score` deliberately excludes unscored jobs: asking for "70 and above" is a question about ranked
    results, and a job with no score yet has no claim to be in that set.
    """

    search: str | None = None
    company: str | None = None
    source: str | None = None
    remote_type: str | None = None
    technology: str | None = None
    status: str | None = None
    min_score: int | None = None
    unscored_only: bool = False

    @property
    def is_empty(self) -> bool:
        return self == JobFilters()
