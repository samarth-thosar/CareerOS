"""ArtifactStore port -- where per-application files are written.

An interface because the destination is a policy decision, not a fact: today a local folder, plausibly later a
synced drive or object storage. Nothing in the tailoring flow should need to change for that.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


class ArtifactStore(Protocol):
    def allocate(self, *, company_name: str, job_title: str, at: datetime) -> Path:
        """Reserve a fresh location for one tailoring run, never reusing an existing one."""
        ...

    def write_json(self, directory: Path, filename: str, payload: dict[str, Any]) -> Path: ...
    def write_text(self, directory: Path, filename: str, content: str) -> Path: ...
