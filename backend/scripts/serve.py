"""Runs the API locally.

Exists only to apply the WMI workaround before uvicorn imports SQLAlchemy. Once the Windows WMI service is
healthy, this is equivalent to:

    uvicorn careeros.presentation.api.app:create_app --factory --reload

    python scripts/serve.py            # 127.0.0.1:8000
    python scripts/serve.py 8001       # a different port
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.wmi_workaround  # noqa: E402,F401  (must precede the uvicorn/SQLAlchemy import)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(
        "careeros.presentation.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
    )
