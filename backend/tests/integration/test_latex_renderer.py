"""Tests for the real LatexRenderer against an actually installed engine.

Kept apart from the tailoring pipeline tests, which use a fake renderer: a real compile takes seconds, fetches
packages on first use, and depends on which engine is installed. These skip when no engine is available so the
suite stays green on a machine without LaTeX, and are marked `slow` so they can be excluded during rapid work:

    pytest -m "not slow"
"""
from __future__ import annotations

from pathlib import Path

import pytest

from careeros.infrastructure.config.settings import load_settings
from careeros.infrastructure.resume.latex_renderer import LatexRenderer

pytestmark = pytest.mark.slow

MINIMAL_TEX = r"""\documentclass{article}
\begin{document}
CareerOS render check.
\end{document}
"""

BROKEN_TEX = r"""\documentclass{article}
\begin{document}
\thisCommandDoesNotExist
\end{document}
"""


def _renderer() -> LatexRenderer:
    return LatexRenderer(engine=load_settings().resume.latex_engine or None)


requires_engine = pytest.mark.skipif(
    not _renderer().is_available(),
    reason="no LaTeX engine installed; see README for how to add tectonic",
)


class TestEngineDiscovery:
    def test_a_bogus_configured_engine_is_reported_unavailable(self) -> None:
        assert LatexRenderer(engine="definitely-not-a-real-engine").is_available() is False

    async def test_missing_engine_reports_unavailable_rather_than_failure(self, tmp_path: Path) -> None:
        result = await LatexRenderer(engine="definitely-not-a-real-engine").render(
            MINIMAL_TEX, tmp_path, "probe"
        )

        assert result.succeeded is False
        assert result.unavailable is True, "an absent toolchain must not look like a broken document"


@requires_engine
class TestRealRendering:
    async def test_compiles_a_minimal_document_to_pdf(self, tmp_path: Path) -> None:
        result = await _renderer().render(MINIMAL_TEX, tmp_path, "probe")

        assert result.succeeded is True
        assert result.pdf_path is not None and result.pdf_path.exists()
        assert result.pdf_path.read_bytes().startswith(b"%PDF")

    async def test_writes_the_tex_alongside_the_pdf(self, tmp_path: Path) -> None:
        await _renderer().render(MINIMAL_TEX, tmp_path, "probe")

        assert (tmp_path / "probe.tex").exists()

    async def test_a_broken_document_fails_without_claiming_unavailable(self, tmp_path: Path) -> None:
        result = await _renderer().render(BROKEN_TEX, tmp_path, "broken")

        assert result.succeeded is False
        assert result.unavailable is False, "a compile error is not a missing toolchain"
        assert result.log

    async def test_the_real_master_resume_compiles(self, tmp_path: Path) -> None:
        """The shipped template must actually build -- otherwise every tailored resume is .tex-only."""
        from careeros.infrastructure.resume.local_tex_resume_source import DEFAULT_MASTER_RESUME_PATH

        result = await _renderer().render(
            DEFAULT_MASTER_RESUME_PATH.read_text(encoding="utf-8"), tmp_path, "master"
        )

        assert result.succeeded is True, f"master template failed to compile: {(result.log or '')[-1500:]}"
