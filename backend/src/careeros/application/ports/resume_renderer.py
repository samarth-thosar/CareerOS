"""ResumeRenderer port -- turns tailored .tex into a PDF.

A port rather than a direct call because compiling LaTeX needs a toolchain that may not be installed. Keeping
it behind an interface means the tailoring pipeline produces its .tex and artifacts regardless, and PDF output
becomes available the moment a toolchain appears -- with no change to any service.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class RenderResult:
    """Outcome of a render attempt.

    `unavailable` distinguishes "no LaTeX toolchain installed" from "the document failed to compile". The first
    is an environment gap the user can fix; the second is a real problem with the document, and conflating them
    would make a broken template look like a missing dependency.
    """

    succeeded: bool
    pdf_path: Path | None = None
    unavailable: bool = False
    log: str | None = None


class ResumeRenderer(Protocol):
    def is_available(self) -> bool: ...
    async def render(self, tex_content: str, output_dir: Path, stem: str) -> RenderResult: ...
