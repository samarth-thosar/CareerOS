"""The infrastructure layer: every concrete adapter, plus the composition root.

Holds all third-party framework dependencies -- SQLAlchemy, Playwright, APScheduler, pydantic-settings --
and the `bootstrap` module that wires their adapters into application services. See
docs/architecture/00-overview.md.
"""
