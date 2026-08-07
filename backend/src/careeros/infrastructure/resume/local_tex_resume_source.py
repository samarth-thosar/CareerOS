"""LocalTexResumeSource -- reads the master resume from a local .tex file.

Chosen over scraping Overleaf because Overleaf's git bridge is a paid feature and its web session is not a
stable interface. Exporting the .tex into data/master/ keeps the workflow free, version-controllable, and
independent of a third party's markup changing.

`version_ref` is a content hash rather than a timestamp, so every ResumeVersion records exactly which master
text it derived from and an unchanged file re-resolves to the same reference.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from careeros.application.ports.resume_source import MasterResumeSnapshot

DEFAULT_MASTER_RESUME_PATH = Path(__file__).resolve().parents[4] / "data" / "master" / "resume.tex"


class MasterResumeMissingError(FileNotFoundError):
    """Raised when the master resume file cannot be found."""


class LocalTexResumeSource:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_MASTER_RESUME_PATH

    async def fetch_master(self) -> MasterResumeSnapshot:
        if not self._path.exists():
            raise MasterResumeMissingError(f"No master resume at {self._path}")
        content = self._path.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return MasterResumeSnapshot(version_ref=f"local:{digest}", content=content)
