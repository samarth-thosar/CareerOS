"""LatexRenderer -- compiles tailored .tex to PDF using whichever local toolchain is installed.

Tries engines in order of preference and reports `unavailable` when none is present, so a machine without
LaTeX still gets its tailored .tex and artifacts; only the PDF step is skipped. Install any one of the engines
below (Tectonic is the smallest) and PDFs start appearing with no code or config change.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from careeros.application.ports.resume_renderer import RenderResult

logger = logging.getLogger(__name__)

# Tectonic first: single binary, fetches only the packages a document actually uses.
_ENGINE_PREFERENCE: tuple[str, ...] = ("tectonic", "pdflatex", "xelatex", "lualatex")

_COMPILE_TIMEOUT_SECONDS = 120


class LatexRenderer:
    def __init__(self, engine: str | None = None) -> None:
        self._configured_engine = engine

    def _resolve_engine(self) -> str | None:
        if self._configured_engine:
            return shutil.which(self._configured_engine)
        for candidate in _ENGINE_PREFERENCE:
            found = shutil.which(candidate)
            if found:
                return found
        return None

    def is_available(self) -> bool:
        return self._resolve_engine() is not None

    async def render(self, tex_content: str, output_dir: Path, stem: str) -> RenderResult:
        engine_path = self._resolve_engine()
        if engine_path is None:
            logger.info(
                "No LaTeX engine found (looked for %s); skipping PDF render", ", ".join(_ENGINE_PREFERENCE)
            )
            return RenderResult(succeeded=False, unavailable=True, log="No LaTeX engine installed")

        output_dir.mkdir(parents=True, exist_ok=True)
        tex_path = output_dir / f"{stem}.tex"
        tex_path.write_text(tex_content, encoding="utf-8")

        command = _build_command(engine_path, tex_path, output_dir)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(output_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=_COMPILE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            # A LaTeX error can leave the engine waiting on stdin forever; batch work must not hang on it.
            return RenderResult(succeeded=False, log=f"{engine_path} timed out after {_COMPILE_TIMEOUT_SECONDS}s")
        except OSError as error:
            return RenderResult(succeeded=False, log=f"Could not run {engine_path}: {error}")

        log = (stdout or b"").decode("utf-8", errors="replace")
        pdf_path = output_dir / f"{stem}.pdf"
        if process.returncode == 0 and pdf_path.exists():
            return RenderResult(succeeded=True, pdf_path=pdf_path, log=log[-4_000:])

        logger.warning("LaTeX render failed for %s (exit %s)", tex_path, process.returncode)
        return RenderResult(succeeded=False, log=log[-4_000:])


def _build_command(engine_path: str, tex_path: Path, output_dir: Path) -> list[str]:
    """Engine-specific flags. `nonstopmode` keeps a compile error from blocking on an interactive prompt."""
    if Path(engine_path).stem.lower() == "tectonic":
        return [engine_path, "--outdir", str(output_dir), "--keep-logs", str(tex_path)]
    return [
        engine_path,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={output_dir}",
        str(tex_path),
    ]
