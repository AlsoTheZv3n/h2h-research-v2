"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

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

from backend.cache import close_redis, get_redis, reset_redis
from backend.config import get_settings
from backend.db import get_session
from backend.ingestion.http import build_client
from backend.main import app
from backend.models import Base
from backend.services import briefs, cancer_briefs, target_briefs

TEST_DB_NAME = "h2h_test"


@pytest.fixture(autouse=True)
def _reset_async_singletons() -> Iterator[None]:
    """Keep loop-bound module state from leaking between tests.

    Two module singletons bind to the event loop that first touched them, and
    pytest-asyncio hands each test a fresh loop: the redis client (get_redis), which
    background enrichment now reaches via invalidate_detail, and any enrichment task
    still in briefs._in_flight. Left alone, a client or a lingering task from one test's
    loop poisons the next with "Event loop is closed".

    Sync on purpose -- so it applies to sync tests too, and so it cannot await (awaiting
    a redis close while a just-cancelled background task still holds a connection hangs).
    Cancelling and dropping the references is enough: the next test rebuilds both.
    """
    yield
    for task in (
        *briefs._in_flight.values(),
        *cancer_briefs._in_flight.values(),
        *target_briefs._in_flight.values(),
    ):
        task.cancel()
    briefs._in_flight.clear()
    cancer_briefs._in_flight.clear()
    target_briefs._in_flight.clear()
    reset_redis()


@pytest.fixture
async def fast_client() -> AsyncIterator[httpx.AsyncClient]:
    """A source client with retries and backoff turned down.

    The production client retries 5xx four times with exponential backoff, which is
    right against a source that 500s as often as ChEMBL -- and turns a mocked
    failure path into minutes of real sleeping. Tests assert the retry policy
    directly (test_adapters); everything else should not pay for it.
    """
    async with build_client(timeout=5.0, attempts=1) as c:
        yield c


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
                # create_all does not know about extensions, so `abstract.embedding`
                # would fail on an unknown type `vector` -- and it would fail at
                # schema build, reading as "postgres is broken" rather than "this
                # database is missing an extension the migration adds". The migration
                # creates it for real databases; this is the same line for the one
                # database Alembic never runs against.
                await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    try:
        asyncio.run(prepare())
    except (sa.exc.OperationalError, sa.exc.InterfaceError, OSError) as exc:  # pragma: no cover
        # Fail, don't skip. A skip here would let CI go green having tested none of
        # the persistence guarantees these tests exist to protect.
        # A connection-level error: postgres really is unreachable, so this advice fits.
        pytest.fail(
            f"postgres unreachable at {dsn}: {exc}\n"
            "Start it with `docker compose up -d postgres`; if it is already up, check "
            "DATABASE_URL in .env for a remapped host port."
        )
    except Exception as exc:  # pragma: no cover - environment, not logic
        # Connected fine, but preparing the schema failed. Do NOT guess "stack is down"
        # here -- that was the precedent bug (a chembl_id one char past varchar(20) read
        # as "the compose stack must be up" while it was up). Name the real class of cause
        # and say plainly that restarting will not help.
        pytest.fail(
            f"the test database at {dsn} was reachable, but preparing its schema failed: {exc}\n"
            "This is a DDL/type error (e.g. a column too small, or a missing extension), not "
            "a stack that is down -- fix the cause named above; `docker compose up` will not help."
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


@pytest.fixture
async def api(db_engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    """An ASGI client whose sessions point at the test database.

    The distinction from `client` is easy to miss and costs an afternoon when you
    do: `client` runs the app against whatever DATABASE_URL says, which is the
    *dev* database. Pair it with the `session` fixture and the two are writing and
    reading different databases -- rows appear to vanish and every lookup 404s.
    Anything that seeds through `session` and reads over HTTP wants this fixture.

    Flushes the cache around each test: Redis outlives the database truncation, so
    without this a cached brief from an earlier test could answer a later one and
    the suite would be testing its own leftovers.

    And disposes the Redis client afterwards. It is a module singleton whose
    connection belongs to the loop that opened it, and pytest-asyncio hands each
    test a fresh loop -- so a client surviving the test poisons the next one.
    """
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override() -> AsyncIterator[object]:
        async with maker() as s:
            yield s

    await get_redis().flushdb()
    app.dependency_overrides[get_session] = _override
    try:
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                yield c
    finally:
        app.dependency_overrides.clear()
        await get_redis().flushdb()
        await close_redis()
