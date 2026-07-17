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


async def test_startup_mutes_httpx_so_the_ncbi_key_cannot_leak_to_logs(
    client: httpx.AsyncClient,
) -> None:
    """httpx logs each request URL at INFO, and NCBI calls carry api_key= in the query
    string -- so at the default INFO level the key prints verbatim to
    `docker compose logs api` on every PubMed request. The pre-release audit
    reproduced it. Startup mutes the httpx logger to WARNING; this locks it, so a
    future logging change that re-opens the leak fails here rather than in production.

    The `client` fixture runs the app lifespan, which is what applies the mute.

    Asserts the httpx logger's OWN level, not getEffectiveLevel(): pytest sets the
    root logger to WARNING for its capture, so the effective level reads WARNING even
    with no mute at all -- the first version of this test used getEffectiveLevel() and
    could not fail. In production root is INFO (from basicConfig), so only httpx's own
    level standing at WARNING actually filters the request-URL line.
    """
    import logging

    assert logging.getLogger("httpx").level >= logging.WARNING
