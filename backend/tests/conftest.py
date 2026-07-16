"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import get_settings
from backend.main import app
from backend.models import Base

TEST_DB_NAME = "h2h_test"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client with the app's lifespan actually run (startup/shutdown included)."""
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _admin_dsn(dsn: str) -> str:
    """Same server, but the maintenance database -- you cannot drop the db you are in."""
    return dsn.rsplit("/", 1)[0] + "/postgres"


def _test_dsn() -> str:
    """DSN for the test database.

    Derived rather than taken from the DSN as-is: these tests create and drop schema,
    and pointing them at a developer's dev database would wipe it.

    Read through settings, not os.environ: pytest does not load .env, so reading the
    environment directly would silently fall back to the default DSN and skip every
    database test as "postgres unreachable" -- a green run that tested nothing.
    """
    dsn = get_settings().database_url
    return dsn.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"


@pytest.fixture(scope="session")
def db_url() -> str:
    """Ensure the test database exists with a current schema; return its DSN.

    Synchronous on purpose. asyncpg connections are bound to the event loop that
    opened them, and pytest-asyncio gives each test a fresh loop -- so a long-lived
    async fixture leaks connections across loops and fails with "another operation is
    in progress". Every engine here is created and disposed inside one short-lived
    loop, so nothing crosses.
    """
    import asyncio

    dsn = _test_dsn()

    async def prepare() -> None:
        admin = create_async_engine(_admin_dsn(dsn), isolation_level="AUTOCOMMIT")
        try:
            async with admin.connect() as conn:
                exists = await conn.scalar(
                    sa.text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}
                )
                if not exists:
                    await conn.execute(sa.text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        finally:
            await admin.dispose()

        engine = create_async_engine(dsn)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    try:
        asyncio.run(prepare())
    except Exception as exc:  # pragma: no cover - environment, not logic
        # Fail, don't skip. A skip here would let CI go green having tested none of
        # the persistence guarantees these tests exist to protect.
        pytest.fail(
            f"postgres unreachable at {dsn}: {exc}\n"
            "Start it with `docker compose up -d postgres`, and check DATABASE_URL "
            "in .env if the host port is remapped."
        )
    return dsn


@pytest.fixture
async def db_engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    """One engine per test, disposed with its loop."""
    engine = create_async_engine(db_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session per test, with the tables emptied afterwards so tests stay independent."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    async with db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(sa.text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
