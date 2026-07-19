"""The lazy target-brief service: state machine, in-flight dedup, stale-while-revalidate.

The target-side twin of test_cancer_enrichment.py's brief-service coverage. Drives
get_or_start_target_brief against a real database with the background session pointed at
db_engine and Open Targets mocked at the HTTP boundary. Pins the invariants a Phase-3 page
depends on: a never-enriched target enriches once (N readers -> ONE fetch), the in-flight
marker is released, and -- the load-bearing ordering -- a READY brief is served READY even
while a background refresh is in flight, never flipped back to ENRICHING (which would blank
the page).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.ingestion.base import FactStatus, utcnow
from backend.repositories.cancers import CancerRepository
from backend.repositories.targets import TargetRepository
from backend.services import target_briefs
from backend.services.briefs import BriefState
from backend.services.target_briefs import get_or_start_target_brief, retry_target_brief

OT = "https://api.platform.opentargets.org/api/v4/graphql"
TARGET = "ENSG_TEST"
LUNG = "MONDO_0005233"


@pytest.fixture(autouse=True)
def clear_in_flight() -> Iterator[None]:
    """Module state; a leak across tests would fake a pass."""
    target_briefs._in_flight.clear()
    yield
    target_briefs._in_flight.clear()


@pytest.fixture
async def catalogued(session: AsyncSession) -> None:
    """A target in the catalog and one cancer for its associated_cancers to match."""
    await CancerRepository(session).upsert_cancer(LUNG, name="lung", n_drugs=1, n_targets=1)
    await TargetRepository(session).upsert_target(TARGET, symbol="KRAS")
    await session.commit()


def _reverse_response(*disease_ids: str) -> httpx.Response:
    rows = [
        {"score": round(0.9 - i * 0.05, 3), "disease": {"id": did, "name": f"cancer {did}"}}
        for i, did in enumerate(disease_ids)
    ]
    return httpx.Response(
        200,
        json={
            "data": {
                "target": {
                    "id": TARGET,
                    "approvedSymbol": "KRAS",
                    "approvedName": "KRAS proto-oncogene",
                    "associatedDiseases": {"count": len(rows), "rows": rows},
                }
            }
        },
    )


class TestTargetBriefState:
    async def test_an_unknown_target_needs_no_enrichment(self, session: AsyncSession) -> None:
        state = await get_or_start_target_brief(session, "ENSG_NOPE")
        assert state is BriefState.NOT_ANALYZED
        assert not target_briefs._in_flight

    async def test_an_enriched_target_is_ready_and_starts_nothing(
        self, session: AsyncSession, catalogued: None
    ) -> None:
        await TargetRepository(session).mark_enriched(TARGET, utcnow())
        await session.commit()
        state = await get_or_start_target_brief(session, TARGET)
        assert state is BriefState.READY
        assert not target_briefs._in_flight


class TestLazyTargetFetch:
    @respx.mock
    async def test_opening_a_never_enriched_target_produces_associated_cancers(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        respx.post(OT).mock(return_value=_reverse_response(LUNG))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        state = await get_or_start_target_brief(session, TARGET, maker=maker)
        assert state is BriefState.ENRICHING
        await target_briefs._in_flight[TARGET]

        async with maker() as fresh:
            repo = TargetRepository(fresh)
            facts = {f.key: f for f in await repo.facts_for(TARGET)}
            assert facts["associated_cancers"].status is FactStatus.OK
            target = await repo.get(TARGET)
            assert target is not None
            assert target.last_enriched_at is not None
            assert target.n_cancers == 1

    @respx.mock
    async def test_concurrent_readers_cause_one_fetch(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        respx.post(OT).mock(return_value=_reverse_response(LUNG))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        states = await asyncio.gather(
            *(get_or_start_target_brief(session, TARGET, maker=maker) for _ in range(5))
        )
        assert all(s is BriefState.ENRICHING for s in states)
        assert len(target_briefs._in_flight) == 1
        await target_briefs._in_flight[TARGET]
        # The dedup that matters: ONE enrich, not five. One enrich is exactly one OT call (the
        # single reverse query). Five enrichments would make five. (len(_in_flight) == 1 alone
        # cannot catch a broken dedup -- five tasks under one key still leave len == 1.)
        assert respx.calls.call_count == 1

    @respx.mock
    async def test_the_in_flight_marker_is_released(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        respx.post(OT).mock(return_value=_reverse_response(LUNG))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        await get_or_start_target_brief(session, TARGET, maker=maker)
        await target_briefs._in_flight[TARGET]
        assert not target_briefs.is_target_enriching(TARGET)


class TestTargetStaleWhileRevalidate:
    @respx.mock
    async def test_a_stale_ready_target_is_served_now_and_refreshed_behind_it(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        await TargetRepository(session).mark_enriched(TARGET, utcnow() - timedelta(days=60))
        await session.commit()
        respx.post(OT).mock(return_value=_reverse_response(LUNG))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        state = await get_or_start_target_brief(session, TARGET, maker=maker)
        assert state is BriefState.READY
        assert target_briefs.is_target_enriching(TARGET), "a stale brief must revalidate behind"
        await target_briefs._in_flight[TARGET]

    async def test_a_ready_target_with_a_refresh_in_flight_stays_ready(
        self, session: AsyncSession, catalogued: None
    ) -> None:
        """The load-bearing ordering: the READY check comes BEFORE the in-flight check, so a
        background refresh never flips a ready brief to ENRICHING and blanks the page. A fresh
        enriched target plus an injected in-flight marker must still read READY."""
        await TargetRepository(session).mark_enriched(TARGET, utcnow())
        await session.commit()

        async def _noop() -> None:
            return None

        target_briefs._in_flight[TARGET] = asyncio.create_task(_noop())
        try:
            state = await get_or_start_target_brief(session, TARGET)
            assert state is BriefState.READY  # NOT ENRICHING, despite the in-flight marker
        finally:
            await target_briefs._in_flight[TARGET]


class TestRetryTargetBrief:
    async def test_retry_of_an_unknown_target_is_not_analyzed(self, session: AsyncSession) -> None:
        state = await retry_target_brief(session, "ENSG_NOPE")
        assert state is BriefState.NOT_ANALYZED

    @respx.mock
    async def test_retry_re_fetches_an_enriched_target(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        await TargetRepository(session).mark_enriched(TARGET, utcnow())
        await session.commit()
        respx.post(OT).mock(return_value=_reverse_response(LUNG))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        state = await retry_target_brief(session, TARGET, maker=maker)
        assert state is BriefState.ENRICHING  # a retry re-fetches even a ready brief
        await target_briefs._in_flight[TARGET]
