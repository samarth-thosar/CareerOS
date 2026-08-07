"""Writes the per-application artifact folder.

One self-contained directory per tailoring run, so months later it is possible to answer "what exactly did I
send this company, and why" without reconstructing anything from logs:

    data/applications/2026-08-08__stripe__backend-engineer/
        job-listing.json    full posting snapshot as discovered
        score.json          the score and its itemized reasoning, when scored
        resume.tex          the tailored source
        resume.pdf          the compiled document, when a LaTeX toolchain is available
        selection.json      exactly which achievements and bullets were chosen
        diff.md             human-readable summary of what changed and why
        gaps.md             requirements the achievement bank could not support

Folders are never overwritten: a second tailoring run for the same job gets a `-2` suffix, preserving every
previous version as the resume requirements demand.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[4] / "data" / "applications"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LENGTH = 40


def slugify(text: str) -> str:
    slug = _SLUG_STRIP.sub("-", (text or "").lower()).strip("-")
    return slug[:_MAX_SLUG_LENGTH].rstrip("-") or "unknown"


@dataclass(slots=True)
class StoredArtifacts:
    directory: Path
    tex_path: Path
    pdf_path: Path | None


class ArtifactStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or DEFAULT_ARTIFACT_ROOT

    @property
    def root(self) -> Path:
        return self._root

    def allocate(self, *, company_name: str, job_title: str, at: datetime) -> Path:
        """Reserve a fresh directory, suffixing rather than reusing one that already exists."""
        base_name = f"{at:%Y-%m-%d}__{slugify(company_name)}__{slugify(job_title)}"
        directory = self._root / base_name
        attempt = 2
        while directory.exists():
            directory = self._root / f"{base_name}-{attempt}"
            attempt += 1
        directory.mkdir(parents=True)
        return directory

    def write_json(self, directory: Path, filename: str, payload: dict[str, Any]) -> Path:
        path = directory / filename
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def write_text(self, directory: Path, filename: str, content: str) -> Path:
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        return path
