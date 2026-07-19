"""The cancer overview's per-facet counts, through the real API. Mirrors the drug facet tests:
each option's count is over the OTHER active filters (its own facet excluded), so a reader sees
what selecting an option would narrow to before clicking it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.models import Cancer
from backend.repositories.cancers import CancerRepository

# (disease_id, name, therapeutic_area, n_drugs)
_ROWS = [
    ("MONDO_F1", "fixture lung", "respiratory or thoracic disease", 5),
    ("MONDO_F2", "fixture breast", "reproductive system or breast disease", 3),
    ("MONDO_F3", "fixture rare", "hematologic disorder", 0),
    ("MONDO_F4", "fixture lung two", "respiratory or thoracic disease", 2),
]


@pytest.fixture
async def catalog(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Seed the fixture cancers (their own sessionmaker, so the `api` client sees committed rows),
    over a clean cancer table so the aggregate facet counts are exactly these rows. Deleted after,
    so they do not leak into a later test that counts or pre-warms the catalog."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(delete(Cancer))  # a clean slate: the counts below assert exact totals
        repo = CancerRepository(s)
        for did, name, area, n_drugs in _ROWS:
            await repo.upsert_cancer(
                did, name=name, therapeutic_area=area, n_drugs=n_drugs, n_targets=10
            )
        await s.commit()
    yield
    async with maker() as s:
        await s.execute(delete(Cancer).where(Cancer.disease_id.in_([r[0] for r in _ROWS])))
        await s.commit()


async def _facets(api: httpx.AsyncClient, **params: object) -> dict[str, dict[str, int]]:
    r = await api.get("/cancers/facets", params={k: str(v) for k, v in params.items()})
    assert r.status_code == 200, r.text
    return {facet: {o["value"]: o["count"] for o in opts} for facet, opts in r.json().items()}


RESP = "respiratory or thoracic disease"
REPRO = "reproductive system or breast disease"
HEME = "hematologic disorder"


class TestCancerFacetCounts:
    async def test_counts_reflect_the_catalog(self, api: httpx.AsyncClient, catalog: None) -> None:
        f = await _facets(api)
        assert f["therapeutic_area"] == {RESP: 2, REPRO: 1, HEME: 1}
        assert f["has_drugs"] == {"true": 3, "false": 1}

    async def test_a_facet_excludes_its_own_selection(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # has_drugs=true selected: the has_drugs facet still shows both options (own clause
        # excluded), while therapeutic_area is counted among drugged cancers only -- the rare
        # cancer (no drugs) drops out of the area counts.
        f = await _facets(api, has_drugs="true")
        assert f["has_drugs"] == {"true": 3, "false": 1}
        assert f["therapeutic_area"] == {RESP: 2, REPRO: 1}

    async def test_area_filter_narrows_has_drugs(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        f = await _facets(api, therapeutic_area=RESP)
        # Among respiratory cancers (both drugged): has_drugs true 2, and no false bucket.
        assert f["has_drugs"] == {"true": 2}
        # The area facet excludes its own clause, so it still shows every area.
        assert f["therapeutic_area"] == {RESP: 2, REPRO: 1, HEME: 1}

    async def test_facets_route_is_not_swallowed_by_the_id_route(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        r = await api.get("/cancers/facets")
        assert r.status_code == 200
        assert isinstance(r.json(), dict) and "therapeutic_area" in r.json()
