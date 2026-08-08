"""FakeResumeRenderer -- stands in for a real LaTeX toolchain in tests.

Two reasons this exists rather than letting tests call the installed engine:

* **Speed and determinism.** A real compile is seconds per document and depends on which engine happens to be
  installed, so the suite would be both slow and machine-dependent.
* **Coverage.** The interesting branches -- toolchain absent, and compile failed -- are hard to arrange for
  real but trivial here, and the "failed" branch must not be confused with "unavailable".

Real rendering is exercised separately in tests/integration/test_latex_renderer.py, which skips when no engine
is present.
"""
from __future__ import annotations

from pathlib import Path

from careeros.application.ports.resume_renderer import RenderResult


class FakeResumeRenderer:
    def __init__(self, *, available: bool = True, succeeds: bool = True) -> None:
        self._available = available
        self._succeeds = succeeds
        self.calls: list[tuple[str, Path, str]] = []

    def is_available(self) -> bool:
        return self._available

    async def render(self, tex_content: str, output_dir: Path, stem: str) -> RenderResult:
        self.calls.append((tex_content, output_dir, stem))
        output_dir.mkdir(parents=True, exist_ok=True)
        # The real renderer writes the .tex before compiling, so artifacts exist either way.
        (output_dir / f"{stem}.tex").write_text(tex_content, encoding="utf-8")

        if not self._available:
            return RenderResult(succeeded=False, unavailable=True, log="No LaTeX engine installed")
        if not self._succeeds:
            return RenderResult(succeeded=False, log="! LaTeX Error: simulated failure")

        pdf_path = output_dir / f"{stem}.pdf"
        pdf_path.write_bytes(b"%PDF-1.5\nfake\n%%EOF\n")
        return RenderResult(succeeded=True, pdf_path=pdf_path, log="fake render ok")
