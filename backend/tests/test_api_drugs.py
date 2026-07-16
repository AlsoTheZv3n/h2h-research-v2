"""Read API, against a real Postgres.

The shape these tests defend is the product's promise: a fact arrives with its
source and its status, and "we could not reach ChEMBL" never arrives looking like
"this drug has no mechanism".
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.cache import close_redis, get_redis
from backend.db import get_session
from backend.ingestion.base import FactStatus, SourceRecord, fact, failed
from backend.main import app
from backend.models import DataMaturity
from backend.repositories import DrugRepository


@pytest.fixture
async def api(db_engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    """An ASGI client whose sessions point at the test database.

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


@pytest.fixture
async def seeded(db_engine: AsyncEngine) -> None:
    """Two drugs: a small molecule with a partly-failed fetch, and the ADC."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        repo = DrugRepository(s)
        await repo.upsert_drug(
            "CHEMBL4594350",
            pref_name="ADAGRASIB",
            drug_type="Small molecule",
            max_phase=4,
            primary_target="KRAS",
            smiles="CCO",
            maturity=DataMaturity.FULL,
        )
        await repo.save_record(
            "CHEMBL4594350",
            SourceRecord(
                "chembl",
                "adagrasib",
                ok=True,
                facts={
                    "smiles": fact("CCO", "chembl", source_url="https://ebi.ac.uk/x"),
                    "n_trials": fact(0, "chembl"),
                    # ChEMBL was down for this one...
                    "moa": failed("chembl", "mechanism: 500 Internal Server Error"),
                },
            ),
        )
        await repo.save_record(
            "CHEMBL4594350",
            SourceRecord(
                "opentargets",
                "adagrasib",
                ok=True,
                # ...but Open Targets answered, so we do have a mechanism.
                facts={"moa": fact("GTPase KRas inhibitor", "opentargets")},
            ),
        )
        await repo.upsert_drug(
            "CHEMBL4297844",
            pref_name="TRASTUZUMAB DERUXTECAN",
            drug_type="Antibody",
            max_phase=4,
            primary_target="ERBB2",
            maturity=DataMaturity.INDEX_ONLY,
        )
        await repo.save_record(
            "CHEMBL4297844",
            SourceRecord(
                "chembl",
                "trastuzumab deruxtecan",
                ok=True,
                facts={"ic50_summary": failed("chembl", "activity: 500")},
            ),
        )
        await s.commit()


class TestOverview:
    async def test_lists_index_columns_only(self, api: httpx.AsyncClient, seeded: None) -> None:
        r = await api.get("/drugs")
        assert r.status_code == 200
        body = r.json()

        assert body["total"] == 2
        row = next(i for i in body["items"] if i["chembl_id"] == "CHEMBL4594350")
        assert row["pref_name"] == "ADAGRASIB"
        assert row["maturity"] == "full"
        # No molecular detail in the overview: it is an index, not a brief.
        assert "smiles" not in row
        assert "facts" not in row

    async def test_the_adc_is_listed_and_honestly_labelled(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        """§8: biologics appear in the overview with an honest maturity indicator --
        not excluded, and not with empty cards pretending to be missing data."""
        r = await api.get("/drugs")
        adc = next(i for i in r.json()["items"] if i["chembl_id"] == "CHEMBL4297844")

        assert adc["drug_type"] == "Antibody"
        assert adc["maturity"] == "index_only"

    async def test_search_is_partial_and_case_insensitive(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        """The first cut matched exactly and case-sensitively, which made the search
        box unusable: people type one character at a time, so every keystroke but the
        last returned nothing. A field that reads as broken, not as strict."""
        for query in ("adagrasib", "ADAGRASIB", "adag", "KRAS", "kras", "CHEMBL4594350"):
            r = await api.get("/drugs", params={"q": query})
            assert r.status_code == 200
            items = r.json()["items"]
            assert any(i["chembl_id"] == "CHEMBL4594350" for i in items), (
                f"q={query!r} found nothing"
            )

    async def test_search_spans_name_id_and_target(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        """One box, because a searcher does not know which field their word lives in."""
        by_name = await api.get("/drugs", params={"q": "trastuzumab"})
        by_id = await api.get("/drugs", params={"q": "chembl4297"})
        by_target = await api.get("/drugs", params={"q": "erbb2"})

        for r in (by_name, by_id, by_target):
            assert [i["chembl_id"] for i in r.json()["items"]] == ["CHEMBL4297844"]

    async def test_search_that_matches_nothing_is_an_empty_page(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        r = await api.get("/drugs", params={"q": "zzzz-no-such-drug"})
        assert r.status_code == 200
        assert r.json()["total"] == 0

    async def test_filters_and_pagination(self, api: httpx.AsyncClient, seeded: None) -> None:
        r = await api.get("/drugs", params={"target": "KRAS"})
        assert r.json()["total"] == 1

        # The target facet is case-insensitive too: it is set from data, and data
        # capitalisation is not the user's problem.
        r = await api.get("/drugs", params={"target": "kras"})
        assert r.json()["total"] == 1

        r = await api.get("/drugs", params={"max_phase": 4})
        assert r.json()["total"] == 2

        r = await api.get("/drugs", params={"limit": 1})
        body = r.json()
        assert len(body["items"]) == 1
        # The total is the corpus, not the page. The spike shipped this exact bug:
        # osimertinib's 383 trials reported as 100 because a page length stood in.
        assert body["total"] == 2

    async def test_unknown_target_yields_an_empty_page_not_an_error(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        r = await api.get("/drugs", params={"target": "NOPE"})
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


class TestDetail:
    async def test_every_fact_carries_provenance(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        r = await api.get("/drugs/CHEMBL4594350")
        assert r.status_code == 200
        body = r.json()

        smiles = body["facts"]["smiles"][0]
        assert smiles["value"] == "CCO"
        assert smiles["status"] == "ok"
        assert smiles["source"] == "chembl"
        assert smiles["source_url"] == "https://ebi.ac.uk/x"
        assert smiles["retrieved_at"]

    async def test_none_and_zero_stay_distinct_in_the_response(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        """The whole point, surviving all the way to JSON.

        Both of these serialize a null-ish value; only `status` tells the client
        that one is a measurement and the other is an outage.
        """
        body = (await api.get("/drugs/CHEMBL4594350")).json()

        zero = body["facts"]["n_trials"][0]
        assert zero["value"] == 0
        assert zero["status"] == "empty"
        assert zero["error"] is None

        outage = next(f for f in body["facts"]["moa"] if f["source"] == "chembl")
        assert outage["value"] is None
        assert outage["status"] == "source_failed"
        assert "500" in outage["error"]

    async def test_disagreeing_sources_are_both_returned(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        """ChEMBL failed on the mechanism, Open Targets did not. Both rows come
        back: picking one would be us making the call, silently."""
        body = (await api.get("/drugs/CHEMBL4594350")).json()

        moa = {f["source"]: f for f in body["facts"]["moa"]}
        assert set(moa) == {"chembl", "opentargets"}
        assert moa["opentargets"]["value"] == "GTPase KRas inhibitor"
        assert moa["opentargets"]["status"] == "ok"

    async def test_a_key_with_one_live_source_is_not_unavailable(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        """We have a mechanism -- from Open Targets. Flagging it missing because
        ChEMBL was down would be as wrong as hiding that ChEMBL was down."""
        body = (await api.get("/drugs/CHEMBL4594350")).json()
        assert "moa" not in body["unavailable"]

    async def test_a_key_where_every_source_failed_is_surfaced(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        """Hoisted to the top level so a client cannot mistake an outage for an
        absence without looking."""
        body = (await api.get("/drugs/CHEMBL4297844")).json()
        assert body["unavailable"] == ["ic50_summary"]

    async def test_unknown_drug_is_404(self, api: httpx.AsyncClient, seeded: None) -> None:
        r = await api.get("/drugs/CHEMBL_NOPE")
        assert r.status_code == 404


class TestCache:
    async def test_second_read_is_served_from_cache(
        self, api: httpx.AsyncClient, seeded: None, db_engine: AsyncEngine
    ) -> None:
        """Proven by removing the data, not by two equal responses.

        Two matching payloads would match even if the cache never fired. So: read
        once, delete the drug out from under it, read again. A 200 the second time
        can only have come from Redis.
        """
        first = await api.get("/drugs/CHEMBL4594350")
        assert first.status_code == 200

        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as s:
            await s.execute(sa.text("DELETE FROM drug WHERE chembl_id = 'CHEMBL4594350'"))
            await s.commit()

        second = await api.get("/drugs/CHEMBL4594350")
        assert second.status_code == 200, "the brief was not cached: it hit a now-empty database"
        # Round-tripping through Redis must not reshape the payload -- in
        # particular the status fields that make a null readable.
        assert first.json() == second.json()

    async def test_cached_payload_keeps_status_and_provenance(
        self, api: httpx.AsyncClient, seeded: None
    ) -> None:
        await api.get("/drugs/CHEMBL4594350")
        body = (await api.get("/drugs/CHEMBL4594350")).json()

        outage = next(f for f in body["facts"]["moa"] if f["source"] == "chembl")
        assert outage["status"] == FactStatus.SOURCE_FAILED.value
        assert outage["value"] is None
        assert body["facts"]["n_trials"][0]["value"] == 0
        assert body["facts"]["n_trials"][0]["status"] == "empty"

    async def test_a_dead_cache_degrades_latency_not_the_answer(
        self, api: httpx.AsyncClient, seeded: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redis is an optimisation. If it dies the brief must still be served."""
        import backend.api.drugs as drugs_api

        class DeadRedis:
            async def get(self, *_: object) -> None:
                raise ConnectionError("redis is down")

            async def setex(self, *_: object) -> None:
                raise ConnectionError("redis is down")

        monkeypatch.setattr(drugs_api, "get_redis", lambda: DeadRedis())

        r = await api.get("/drugs/CHEMBL4594350")
        assert r.status_code == 200
        assert r.json()["facts"]["smiles"][0]["value"] == "CCO"
