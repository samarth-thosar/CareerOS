"""Pytest configuration.

pytest imports conftest before any test module, which makes it the right place to apply the WMI workaround:
it has to run before anything imports SQLAlchemy. See scripts/wmi_workaround.py for why that matters and how
to remove it once the Windows WMI service is healthy again.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.wmi_workaround  # noqa: E402,F401  (importing it applies it)


import pytest


@pytest.fixture(autouse=True)
def _no_llm_retry_pause(monkeypatch):
    """Remove the Ollama retry pause in tests.

    The pause exists so a real model load has time to finish; in tests every backend is a stub, so waiting three
    seconds per retry would only make the suite slow.
    """
    monkeypatch.setattr(
        "careeros.infrastructure.llm.ollama_provider._RETRY_PAUSE_SECONDS", 0, raising=False
    )
