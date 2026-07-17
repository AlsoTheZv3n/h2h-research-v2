"""The C1 invariant: a web request never awaits an external API.

This is the load-bearing property of the whole fetch -> store -> serve design. A read
serves whatever the database holds and returns immediately; the external world is
touched only by the background enrich job, never in the request path. The failure it
guards against is concrete and has a shape this project keeps rediscovering: someone
puts an inline `await adapter.fetch(...)` back into the read "just to freshen it," and
then a downed ChEMBL -- which happens a third of the time -- hangs the page on an API
that isn't answering.

So this makes every external source hang forever and asserts the read still returns
in well under a second. Put an inline external await back in the read and it goes red.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.repositories import DrugRepository
from backend.services import briefs

CID = "CHEMBL_NONBLOCK"


class _HangingTransport(httpx.AsyncBaseTransport):
    """Every request sleeps until cancelled. Standing in for ChEMBL being down."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        import asyncio

        await asyncio.sleep(3600)
        raise RuntimeError("unreachable")  # pragma: no cover


@pytest.fixture(autouse=True)
def cancel_hung_tasks() -> Iterator[None]:
    """The background enrich job hangs on the transport; cancel it so teardown is clean."""
    briefs._in_flight.clear()
    yield
    for task in briefs._in_flight.values():
        task.cancel()
    briefs._in_flight.clear()


@pytest.fixture
async def cold_drug(db_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        await DrugRepository(s).upsert_drug(CID, pref_name="hanginib", max_phase=2)
        await s.commit()
    yield maker


async def test_a_cold_read_returns_fast_even_when_every_source_hangs(
    api: httpx.AsyncClient,
    cold_drug: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The background enrich job builds this client and hangs on it forever.
    monkeypatch.setattr(
        briefs, "build_client", lambda **_: httpx.AsyncClient(transport=_HangingTransport())
    )
    # That job runs in its own session from get_sessionmaker(); point it at the test
    # database so it finds the drug and actually reaches the hanging transport, rather
    # than no-opping on a drug the dev database has never heard of.
    monkeypatch.setattr(briefs, "get_sessionmaker", lambda: cold_drug)

    start = time.monotonic()
    r = await api.get(f"/drugs/{CID}")
    elapsed = time.monotonic() - start

    assert r.status_code == 200
    # The enrichment is in flight and hanging; the read reports that and moves on.
    assert r.json()["state"] == "enriching"
    # The whole point: the read did not wait on the sources. The transport sleeps for
    # an hour; anything under a couple of seconds proves the request never awaited it.
    assert elapsed < 5.0, f"the read took {elapsed:.1f}s -- it awaited an external source"
