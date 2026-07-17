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
    """Both dependencies are up, so readiness says so -- specifically.

    This asserted `isinstance(body["ready"], bool)`, which would have passed with
    readiness hardcoded to False. A test that cannot fail is not a test.
    """
    r = await client.get("/health/ready")

    assert r.status_code == 200
    assert r.json() == {"ready": True, "checks": {"postgres": "ok", "redis": "ok"}}


async def test_ready_names_the_dependency_that_is_down(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The claim the docstring makes: reports, rather than raises.

    Nothing exercised it -- no dependency was ever brought down, so "reports each
    dependency instead of raising" was an assertion about code nobody ran.
    """
    import backend.main as main

    class DeadRedis:
        async def ping(self) -> None:
            raise ConnectionError("redis is down")

    monkeypatch.setattr(main, "get_redis", lambda: DeadRedis())

    r = await client.get("/health/ready")

    # 200, not 500: a probe that raises tells the operator nothing about which half
    # is broken.
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["redis"].startswith("error:")
    assert "down" in body["checks"]["redis"]
