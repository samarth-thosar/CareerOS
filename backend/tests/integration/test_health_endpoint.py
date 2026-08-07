"""Integration test: boots the real FastAPI app through the real composition root and hits GET /health.

Proves the async engine, session factory, and scheduler lifespan wiring work end to end -- not just that
the domain logic is correct in isolation.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from careeros.presentation.api.app import create_app


@pytest.fixture
def sqlite_database_url(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("CAREEROS_DATABASE_URL", url)
    return url


async def test_health_endpoint_returns_ok(sqlite_database_url: str) -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
