"""The retry path: look at the sources again for a brief that already has failures.

The normal path serves a READY brief from storage and never re-fetches -- correct for
the common case, wrong for the one where a source was down when we last looked. Retry
forces the re-fetch the normal path skips, and the endpoint invalidates the cached
brief so the reader is not served the stale, still-failed copy while the retry runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.cache import get_redis
from backend.ingestion.base import utcnow
from backend.repositories import DrugRepository
from backend.services import briefs
from backend.services.briefs import BriefState, get_or_start_brief, retry_brief

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
CT = "https://clinicaltrials.gov/api/v2/studies"
OT = "https://api.platform.opentargets.org/api/v4/graphql"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@pytest.fixture(autouse=True)
def clear_in_flight() -> Iterator[None]:
    briefs._in_flight.clear()
    yield
    briefs._in_flight.clear()


def _mock_sources() -> None:
    respx.get(f"{CHEMBL}/molecule/search.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "molecules": [
                    {
                        "molecule_chembl_id": "CHEMBL_NEW",
                        "pref_name": "NEWDRUG",
                        "molecule_synonyms": [],
                        "molecule_structures": {"canonical_smiles": "CCO"},
                        "molecule_properties": {"full_mwt": "100.0"},
                        "max_phase": "2",
                    }
                ]
            },
        )
    )
    respx.get(f"{CHEMBL}/mechanism.json").mock(
        return_value=httpx.Response(200, json={"mechanisms": []})
    )
    respx.get(f"{CHEMBL}/activity.json").mock(
        return_value=httpx.Response(200, json={"page_meta": {"total_count": 0}, "activities": []})
    )
    respx.get(CT).mock(return_value=httpx.Response(200, json={"totalCount": 3, "studies": []}))
    respx.post(OT).mock(
        side_effect=[
            httpx.Response(200, json={"data": {"search": {"hits": [{"id": "CHEMBL_NEW"}]}}}),
            httpx.Response(
                200,
                json={
                    "data": {
                        "drug": {
                            "id": "CHEMBL_NEW",
                            "drugType": "Small molecule",
                            "maximumClinicalStage": "PHASE_2",
                            "mechanismsOfAction": {"rows": []},
                            "indications": {"count": 0, "rows": []},
                        }
                    }
                },
            ),
        ]
    )
    respx.get(f"{EUTILS}/esearch.fcgi").mock(
        return_value=httpx.Response(200, json={"esearchresult": {"count": "7", "idlist": []}})
    )


@pytest.fixture
async def enriched(session: AsyncSession) -> None:
    """A drug already marked enriched, but carrying no facts yet -- so a re-fetch is
    observable as facts appearing where the normal path would have added none."""
    await DrugRepository(session).upsert_drug(
        "CHEMBL_NEW",
        pref_name="NEWDRUG",
        drug_type="Small molecule",
        max_phase=2,
        last_enriched_at=utcnow(),
    )
    await session.commit()


class TestRetryService:
    async def test_unknown_drug_is_not_analyzed_and_starts_nothing(
        self, session: AsyncSession
    ) -> None:
        state = await retry_brief(session, "CHEMBL_NOPE")
        assert state is BriefState.NOT_ANALYZED
        assert not briefs.is_enriching("CHEMBL_NOPE")

    @respx.mock
    async def test_retry_refetches_a_drug_the_normal_path_leaves_alone(
        self, session: AsyncSession, enriched: None, db_engine: AsyncEngine
    ) -> None:
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        # The normal path is done with this drug -- READY, no fetch, no facts added.
        assert await get_or_start_brief(session, "CHEMBL_NEW", maker=maker) is BriefState.READY
        assert not briefs.is_enriching("CHEMBL_NEW")
        async with maker() as check:
            assert list(await DrugRepository(check).facts_for("CHEMBL_NEW")) == []

        # Retry forces the re-fetch it skipped.
        _mock_sources()
        state = await retry_brief(session, "CHEMBL_NEW", maker=maker)
        assert state is BriefState.ENRICHING
        await briefs._in_flight["CHEMBL_NEW"]

        async with maker() as fresh:
            rows = await DrugRepository(fresh).facts_for("CHEMBL_NEW")
            assert {r.source for r in rows} >= {"clinicaltrials", "opentargets", "pubmed"}, (
                "retry did not re-fetch the sources"
            )


@pytest.fixture
async def no_background_enrich(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Neuter the background task for endpoint tests: we assert the endpoint's own
    contract (404, cache invalidation, state), not the fetch, which the service tests
    above cover against a mocked network."""

    async def _noop(chembl_id: str, maker: object) -> None:
        return None

    monkeypatch.setattr(briefs, "_enrich_in_background", _noop)
    yield


class TestRetryEndpoint:
    async def test_404_for_an_unknown_drug(self, api: httpx.AsyncClient) -> None:
        r = await api.post("/drugs/CHEMBL_NOPE/retry")
        assert r.status_code == 404

    async def test_invalidates_the_cached_brief_and_reports_enriching(
        self, api: httpx.AsyncClient, session: AsyncSession, no_background_enrich: None
    ) -> None:
        await DrugRepository(session).upsert_drug(
            "CHEMBL_C", pref_name="C", last_enriched_at=utcnow()
        )
        await session.commit()

        # A stale cached brief sits in front of the reader.
        cache_key = "drug:detail:CHEMBL_C"
        await get_redis().set(cache_key, '{"stale": true}')
        assert await get_redis().get(cache_key) is not None

        r = await api.post("/drugs/CHEMBL_C/retry")
        assert r.status_code == 200
        assert r.json()["state"] == "enriching"
        # The stale copy is gone, or the retry would re-fetch behind a cache that keeps
        # serving the old, still-failed brief until the TTL.
        assert await get_redis().get(cache_key) is None
