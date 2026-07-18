"""Lazy, on-demand enrichment and its fourth state.

`not_analyzed` is the state this project keeps having to invent at each new layer:
"we have not looked" is not "we looked and found nothing", and it is not "we looked
and the source fell over". Three different sentences, and only the last two existed
before this.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.ingestion.base import FactStatus, SourceRecord, fact, utcnow
from backend.models import Drug
from backend.repositories import DrugRepository
from backend.services import briefs
from backend.services.briefs import BriefState, get_or_start_brief

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
CT = "https://clinicaltrials.gov/api/v2/studies"
OT = "https://api.platform.opentargets.org/api/v4/graphql"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@pytest.fixture(autouse=True)
def clear_in_flight() -> Iterator[None]:
    """The in-flight map is module state; a leak across tests would fake a pass."""
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
async def catalogued(session: AsyncSession) -> None:
    """A drug as the catalog loader leaves it: index columns, never enriched."""
    await DrugRepository(session).upsert_drug(
        "CHEMBL_NEW", pref_name="NEWDRUG", drug_type="Small molecule", max_phase=2
    )
    await session.commit()


class TestState:
    async def test_a_never_enriched_drug_is_not_analyzed_not_empty(
        self, session: AsyncSession, catalogued: None
    ) -> None:
        """The distinction the whole feature rests on. This drug has no facts -- and
        that says nothing at all about the drug, only about us."""
        drug = await session.get(Drug, "CHEMBL_NEW")
        assert drug is not None
        assert drug.last_enriched_at is None
        assert list(await DrugRepository(session).facts_for("CHEMBL_NEW")) == []

    async def test_an_unknown_drug_needs_no_enrichment(self, session: AsyncSession) -> None:
        state = await get_or_start_brief(session, "CHEMBL_DOES_NOT_EXIST")
        assert state is BriefState.NOT_ANALYZED
        assert not briefs.is_enriching("CHEMBL_DOES_NOT_EXIST")

    async def test_an_enriched_drug_is_ready_and_starts_nothing(
        self, session: AsyncSession
    ) -> None:
        repo = DrugRepository(session)
        await repo.upsert_drug("CHEMBL_DONE", pref_name="DONE")
        await repo.save_record(
            "CHEMBL_DONE",
            SourceRecord("chembl", "done", ok=True, facts={"smiles": fact("CCO", "chembl")}),
        )
        from backend.ingestion.base import utcnow

        await repo.upsert_drug("CHEMBL_DONE", last_enriched_at=utcnow())
        await session.commit()

        state = await get_or_start_brief(session, "CHEMBL_DONE")

        assert state is BriefState.READY
        # Crucially: no background fetch. A cached drug must not re-hit ChEMBL on
        # every page view.
        assert not briefs.is_enriching("CHEMBL_DONE")


class TestLazyFetch:
    @respx.mock
    async def test_opening_a_never_enriched_drug_produces_a_real_brief(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """The feature: no upfront job, just open it and the facts arrive."""
        _mock_sources()
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        state = await get_or_start_brief(session, "CHEMBL_NEW", maker=maker)
        assert state is BriefState.ENRICHING

        # Wait for the background task the way the UI does: by asking again.
        task = briefs._in_flight.get("CHEMBL_NEW")
        assert task is not None
        await task

        async with maker() as fresh:
            rows = await DrugRepository(fresh).facts_for("CHEMBL_NEW")
            assert rows, "lazy enrichment produced no facts"
            assert {r.source for r in rows} >= {"clinicaltrials", "opentargets", "pubmed"}

            drug = await fresh.get(Drug, "CHEMBL_NEW")
            assert drug is not None
            # Stamped: the next reader gets it from Postgres, not from ChEMBL.
            assert drug.last_enriched_at is not None

    @respx.mock
    async def test_concurrent_readers_cause_one_fetch(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """Ten people opening the same page must not mean ten ChEMBL fetches. The
        source is fragile enough without us multiplying the load."""
        _mock_sources()
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        states = await asyncio.gather(
            *(get_or_start_brief(session, "CHEMBL_NEW", maker=maker) for _ in range(5))
        )

        assert all(s is BriefState.ENRICHING for s in states)
        assert len(briefs._in_flight) == 1
        await briefs._in_flight["CHEMBL_NEW"]

    @respx.mock
    async def test_a_failing_source_leaves_an_honest_brief_not_a_crash(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """ChEMBL 500s a third of the time. That must degrade the brief, not the app,
        and the drug must still count as looked-at so the page stops saying
        "analyzing" forever."""
        _mock_sources()
        respx.get(f"{CHEMBL}/molecule/search.json").mock(return_value=httpx.Response(500))

        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        await get_or_start_brief(session, "CHEMBL_NEW", maker=maker)

        await briefs._in_flight["CHEMBL_NEW"]

        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as fresh:
            drug = await fresh.get(Drug, "CHEMBL_NEW")
            assert drug is not None
            assert drug.last_enriched_at is not None, "a failed look is still a look"
            rows = await DrugRepository(fresh).facts_for("CHEMBL_NEW")

            # The other three sources still answered: one dead source is not a dead brief.
            assert {r.source for r in rows} >= {"clinicaltrials", "opentargets", "pubmed"}

            # And ChEMBL's outage is *recorded*. This assertion used to read
            # `== {"clinicaltrials", "opentargets", "pubmed"}` -- pinning, as correct,
            # a brief that carried no ChEMBL rows at all. With none, `unavailable`
            # comes back empty and the API positively states that nothing failed,
            # while the page says "Not collected" for a mechanism nobody could ask
            # about. The founding lie, frozen by its own test.
            chembl_rows = {r.key: r for r in rows if r.source == "chembl"}
            assert chembl_rows, "a ChEMBL outage left no trace in the brief"
            assert all(r.status is FactStatus.SOURCE_FAILED for r in chembl_rows.values())
            assert {"smiles", "moa", "ic50_summary"} <= set(chembl_rows)
            assert "500" in (chembl_rows["smiles"].error or "")

    @respx.mock
    async def test_a_source_that_does_not_know_the_drug_is_not_an_outage(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """ "ChEMBL has no molecule named X" is an answer, not a failure.

        The mirror image of the test above, and the reason `outage` exists as its own
        flag rather than being inferred from `error`. Writing source_failed rows here
        would claim the source broke when it simply replied "never heard of it" --
        the same lie pointed the other way.
        """
        _mock_sources()
        respx.get(f"{CHEMBL}/molecule/search.json").mock(
            return_value=httpx.Response(200, json={"molecules": []})
        )

        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        await get_or_start_brief(session, "CHEMBL_NEW", maker=maker)
        await briefs._in_flight["CHEMBL_NEW"]

        async with maker() as fresh:
            rows = await DrugRepository(fresh).facts_for("CHEMBL_NEW")
            assert not [r for r in rows if r.source == "chembl"], (
                "a source with no opinion must not be recorded as having failed"
            )

    @respx.mock
    async def test_the_in_flight_marker_is_released(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """A leaked marker would pin the drug in "enriching" until a restart."""
        _mock_sources()
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        await get_or_start_brief(session, "CHEMBL_NEW", maker=maker)
        await briefs._in_flight["CHEMBL_NEW"]

        assert not briefs.is_enriching("CHEMBL_NEW")


class TestStaleWhileRevalidate:
    async def _set_enriched(self, session: AsyncSession, *, days_ago: float) -> None:
        await DrugRepository(session).upsert_drug(
            "CHEMBL_NEW", last_enriched_at=utcnow() - timedelta(days=days_ago)
        )
        await session.commit()

    @respx.mock
    async def test_a_stale_ready_drug_is_served_now_and_refreshed_behind_it(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """The reader gets the stored brief immediately (READY, never blocked), and a
        refresh runs behind it so the next view is fresh. Never ENRICHING -- there ARE
        facts, and blanking the page to re-fetch what we already hold would be a
        regression, not freshness."""
        await self._set_enriched(session, days_ago=60)  # past the 30-day window
        _mock_sources()
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        state = await get_or_start_brief(session, "CHEMBL_NEW", maker=maker)
        assert state is BriefState.READY
        assert briefs.is_enriching("CHEMBL_NEW"), "a stale brief must revalidate in the background"

        await briefs._in_flight["CHEMBL_NEW"]
        async with maker() as fresh:
            drug = await fresh.get(Drug, "CHEMBL_NEW")
            assert drug is not None
            # The refresh landed: the clock moved out of the stale window.
            assert drug.last_enriched_at is not None
            assert drug.last_enriched_at > utcnow() - timedelta(days=1)

    async def test_a_fresh_drug_is_not_revalidated(
        self, session: AsyncSession, catalogued: None
    ) -> None:
        """Freshness is the point: a recently-enriched brief must not re-fetch on every
        open, or stale-while-revalidate becomes revalidate-always -- the tight loop the
        whole freshness design exists to avoid."""
        await self._set_enriched(session, days_ago=1)  # well within the window

        state = await get_or_start_brief(session, "CHEMBL_NEW")
        assert state is BriefState.READY
        assert not briefs.is_enriching("CHEMBL_NEW")
