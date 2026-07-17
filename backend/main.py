"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text

from backend import __version__
from backend.api import chat_router, drugs_router
from backend.cache import close_redis, get_redis
from backend.config import get_settings
from backend.db import dispose_engine, get_sessionmaker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    # httpx logs every request URL at INFO, and our NCBI calls carry api_key= as a
    # query param -- so at the default INFO level `docker compose logs api` prints the
    # key verbatim on every PubMed request. The pre-release audit reproduced it. This
    # is the same leak class safe_error() closed on the fact-serving path, on the
    # logging path instead; WARNING keeps httpx's real errors and drops the URL line.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logger.info("starting h2h %s (%s)", __version__, settings.environment)
    yield
    await dispose_engine()
    await close_redis()


app = FastAPI(
    title="H2H",
    version=__version__,
    summary="Sourced evidence briefs for oncology drug programs.",
    lifespan=lifespan,
)

app.include_router(drugs_router)
app.include_router(chat_router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness. Deliberately dependency-free.

    This is what the container HEALTHCHECK hits: a slow database must not make the
    API look dead and trigger a restart loop. Dependency state lives on /health/ready.
    """
    return {"status": "ok", "version": __version__}


@app.get("/health/ready", tags=["ops"])
async def ready() -> dict[str, Any]:
    """Readiness: can we actually reach Postgres and Redis?"""
    checks: dict[str, str] = {}

    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    ready = all(v == "ok" for v in checks.values())
    return {"ready": ready, "checks": checks}
