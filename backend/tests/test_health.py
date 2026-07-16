"""Health endpoint contract."""

from __future__ import annotations

import httpx
import pytest


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_health_needs_no_database(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liveness must not touch Postgres or Redis.

    The container HEALTHCHECK hits this endpoint, and compose restarts the API when
    it fails. If a slow database could fail it, a database blip would take the API
    down with it. Point the DSN at a dead host and the answer must still be 200.
    """
    from backend import db

    monkeypatch.setattr(
        db, "get_sessionmaker", lambda: (_ for _ in ()).throw(RuntimeError("db is down"))
    )
    r = await client.get("/health")
    assert r.status_code == 200


async def test_ready_reports_per_dependency(client: httpx.AsyncClient) -> None:
    """Readiness reports each dependency instead of raising when one is down."""
    r = await client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert set(body["checks"]) == {"postgres", "redis"}
    assert isinstance(body["ready"], bool)
