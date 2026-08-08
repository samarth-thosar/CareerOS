"""Temporary workaround for a wedged Windows WMI service.

WHY THIS EXISTS
---------------
On this machine the Windows Management Instrumentation service (Winmgmt) stopped responding. Anything that
queries it blocks forever, and `platform.uname()` queries it for processor info on Windows. SQLAlchemy imports
`platform`, so `import sqlalchemy` hangs -- which takes down uvicorn, alembic and every integration test, while
unrelated imports (httpx, pydantic, fastapi) stay fine. That asymmetry is what makes the cause non-obvious.

`platform.uname()` memoises into `platform._uname_cache`. Seeding that cache before anything imports SQLAlchemy
means the WMI query never happens.

THIS IS NOT A FIX
-----------------
The real fix is restarting the service (`net stop winmgmt && net start winmgmt`, as administrator) or rebooting.
Delete this file once that is done -- it is opt-in precisely so it cannot quietly mask the problem returning:
nothing imports it unless a launcher does so explicitly.

USAGE
    python -c "import scripts.wmi_workaround; ..."      # or
    python scripts/dev.py serve                          # which applies it for you
"""
from __future__ import annotations

import platform


def apply() -> bool:
    """Seed platform's uname cache if it is empty. Returns whether this call seeded it."""
    if getattr(platform, "_uname_cache", None) is not None:
        return False

    # Literals only. platform.release() and platform.version() both resolve through uname() themselves, so
    # calling them here would trigger the exact WMI query this is meant to avoid -- the values are cosmetic
    # anyway, since nothing in CareerOS branches on them.
    platform._uname_cache = platform.uname_result(  # type: ignore[attr-defined]
        "Windows",
        "localhost",
        "11",
        "10.0",
        "AMD64",
    )
    return True


apply()
