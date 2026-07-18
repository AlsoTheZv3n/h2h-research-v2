"""Lazy cancer enrichment: the disease-side full loop and its honest states.

Mirrors test_lazy_enrichment.py. The full-loop test runs the real
get_or_start_cancer_brief on an unseeded database with the background session pointed at
the test DB and only the Open Targets HTTP mocked -- so a wiring break (a source that
never saves, an outage stored as "no targets") fails it rather than passing quietly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, cast

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.ingestion import enrich_cancer
from backend.ingestion.base import FactStatus, utcnow
from backend.models import Cancer
from backend.repositories.cancers import CancerRepository
from backend.services import cancer_briefs
from backend.services.briefs import BriefState
from backend.services.cancer_briefs import get_or_start_cancer_brief

OT = "https://api.platform.opentargets.org/api/v4/graphql"
DISEASE = "MONDO_0005233"


@pytest.fixture(autouse=True)
def clear_in_flight() -> Iterator[None]:
    """Module state; a leak across tests would fake a pass."""
    cancer_briefs._in_flight.clear()
    yield
    cancer_briefs._in_flight.clear()


def _landscape_response(*symbols: str) -> httpx.Response:
    """An Open Targets target-landscape answer for the given top targets."""
    rows = [
        {
            "score": round(0.9 - i * 0.1, 3),
            "datatypeScores": [
                {"id": "clinical", "score": 0.5},
                {"id": "somatic_mutation", "score": 0.3},
            ],
            "target": {
                "approvedSymbol": sym,
                "tractability": [
                    {"label": "Approved Drug", "modality": "SM", "value": True},
                    {"label": "Approved Drug", "modality": "AB", "value": False},
                ],
            },
        }
        for i, sym in enumerate(symbols)
    ]
    return httpx.Response(
        200,
        json={
            "data": {
                "disease": {"id": DISEASE, "associatedTargets": {"count": len(rows), "rows": rows}}
            }
        },
    )


@pytest.fixture
async def catalogued(session: AsyncSession) -> None:
    """A cancer as the catalog loader leaves it: index columns, never enriched."""
    await CancerRepository(session).upsert_cancer(
        DISEASE,
        name="non-small cell lung carcinoma",
        therapeutic_area="respiratory or thoracic disease",
        n_drugs=1072,
        n_targets=12475,
    )
    await session.commit()


class TestState:
    async def test_a_never_enriched_cancer_has_no_facts(
        self, session: AsyncSession, catalogued: None
    ) -> None:
        cancer = await session.get(Cancer, DISEASE)
        assert cancer is not None
        assert cancer.last_enriched_at is None
        assert list(await CancerRepository(session).facts_for(DISEASE)) == []

    async def test_an_unknown_cancer_needs_no_enrichment(self, session: AsyncSession) -> None:
        state = await get_or_start_cancer_brief(session, "MONDO_NOPE")
        assert state is BriefState.NOT_ANALYZED
        assert not cancer_briefs.is_cancer_enriching("MONDO_NOPE")

    async def test_an_enriched_cancer_is_ready_and_starts_nothing(
        self, session: AsyncSession, catalogued: None
    ) -> None:
        await CancerRepository(session).mark_enriched(DISEASE, utcnow())
        await session.commit()
        state = await get_or_start_cancer_brief(session, DISEASE)
        assert state is BriefState.READY
        # No background fetch for an already-enriched cancer.
        assert not cancer_briefs.is_cancer_enriching(DISEASE)


class TestLazyFetch:
    @respx.mock
    async def test_opening_a_never_enriched_cancer_produces_a_target_landscape(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """The feature: no upfront job, just open it and the target landscape arrives."""
        respx.post(OT).mock(return_value=_landscape_response("EGFR", "KRAS", "ALK"))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        state = await get_or_start_cancer_brief(session, DISEASE, maker=maker)
        assert state is BriefState.ENRICHING

        await cancer_briefs._in_flight[DISEASE]

        async with maker() as fresh:
            rows = await CancerRepository(fresh).facts_for(DISEASE)
            assert rows, "lazy enrichment produced no facts"
            by_key = {r.key: r for r in rows}
            tl = by_key.get("target_landscape")
            assert tl is not None
            assert tl.source == "opentargets"
            assert tl.status is FactStatus.OK
            assert tl.source_url and DISEASE in tl.source_url
            landscape = cast(list[dict[str, Any]], tl.value)
            assert [t["symbol"] for t in landscape] == ["EGFR", "KRAS", "ALK"]
            # Tractability and evidence channels made it through the mapping.
            assert landscape[0]["sm_tractable"] is True
            assert landscape[0]["ab_tractable"] is False
            assert "clinical" in landscape[0]["evidence_types"]

            cancer = await fresh.get(Cancer, DISEASE)
            assert cancer is not None
            # Stamped: the next reader gets it from Postgres, not from Open Targets.
            assert cancer.last_enriched_at is not None

    @respx.mock
    async def test_an_ot_outage_is_a_source_failed_fact_not_no_targets(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """An outage must land as source_failed, never as an empty landscape -- "Open
        Targets was down" is not "this cancer has no targets"."""
        # 200-with-errors: Open Targets' partial-failure shape (and not retried, being a 200).
        respx.post(OT).mock(
            return_value=httpx.Response(200, json={"errors": [{"message": "boom"}]})
        )
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        await get_or_start_cancer_brief(session, DISEASE, maker=maker)
        await cancer_briefs._in_flight[DISEASE]

        async with maker() as fresh:
            rows = await CancerRepository(fresh).facts_for(DISEASE)
            tl = {r.key: r for r in rows}.get("target_landscape")
            assert tl is not None, "an Open Targets outage left no trace in the brief"
            assert tl.status is FactStatus.SOURCE_FAILED  # NOT empty
            assert tl.value is None

            cancer = await fresh.get(Cancer, DISEASE)
            assert cancer is not None
            assert cancer.last_enriched_at is not None, "a failed look is still a look"

    @respx.mock
    async def test_a_disease_ot_cannot_resolve_writes_no_fact_not_empty(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """Open Targets answers 200 but does not resolve the disease id (deprecated or
        remapped). That is a lookup failure, not "no targets": no EMPTY fact is written,
        so the card never claims this cancer has zero druggable biology."""
        respx.post(OT).mock(return_value=httpx.Response(200, json={"data": {"disease": None}}))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        await get_or_start_cancer_brief(session, DISEASE, maker=maker)
        await cancer_briefs._in_flight[DISEASE]

        async with maker() as fresh:
            rows = await CancerRepository(fresh).facts_for(DISEASE)
            # No target_landscape fact at all -- never an EMPTY that reads as "no targets".
            assert not any(r.key == "target_landscape" for r in rows)
            cancer = await fresh.get(Cancer, DISEASE)
            assert cancer is not None
            assert cancer.last_enriched_at is not None, "we still looked"

    @respx.mock
    async def test_concurrent_readers_cause_one_fetch(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        respx.post(OT).mock(return_value=_landscape_response("EGFR"))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        states = await asyncio.gather(
            *(get_or_start_cancer_brief(session, DISEASE, maker=maker) for _ in range(5))
        )
        assert all(s is BriefState.ENRICHING for s in states)
        assert len(cancer_briefs._in_flight) == 1
        await cancer_briefs._in_flight[DISEASE]
        # The dedup that matters: ONE enrich, not five. One enrich makes one OT call per
        # source; five would make five times that. (The in-flight dict length alone cannot
        # catch a broken dedup -- five tasks under the same key still leave len == 1.)
        assert respx.calls.call_count == len(enrich_cancer.build_cancer_sources())

    @respx.mock
    async def test_the_in_flight_marker_is_released(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        respx.post(OT).mock(return_value=_landscape_response("EGFR"))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        await get_or_start_cancer_brief(session, DISEASE, maker=maker)
        await cancer_briefs._in_flight[DISEASE]
        assert not cancer_briefs.is_cancer_enriching(DISEASE)


class TestStaleWhileRevalidate:
    async def _set_enriched(self, session: AsyncSession, *, days_ago: float) -> None:
        await CancerRepository(session).mark_enriched(DISEASE, utcnow() - timedelta(days=days_ago))
        await session.commit()

    @respx.mock
    async def test_a_stale_ready_cancer_is_served_now_and_refreshed_behind_it(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        await self._set_enriched(session, days_ago=60)  # past the 30-day window
        respx.post(OT).mock(return_value=_landscape_response("EGFR"))
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        state = await get_or_start_cancer_brief(session, DISEASE, maker=maker)
        assert state is BriefState.READY
        assert cancer_briefs.is_cancer_enriching(DISEASE), "a stale brief must revalidate behind"

        await cancer_briefs._in_flight[DISEASE]
        async with maker() as fresh:
            cancer = await fresh.get(Cancer, DISEASE)
            assert cancer is not None
            # The refresh landed: the clock moved out of the stale window.
            assert cancer.last_enriched_at is not None
            assert cancer.last_enriched_at > utcnow() - timedelta(days=1)

    async def test_a_fresh_cancer_is_not_revalidated(
        self, session: AsyncSession, catalogued: None
    ) -> None:
        await self._set_enriched(session, days_ago=1)  # well within the window
        state = await get_or_start_cancer_brief(session, DISEASE)
        assert state is BriefState.READY
        assert not cancer_briefs.is_cancer_enriching(DISEASE)


def _pipeline_response(*drugs: tuple[str, str, str]) -> httpx.Response:
    """An Open Targets disease->drugs answer: (chembl_id, name, stage) tuples."""
    rows = [{"drug": {"id": c, "name": n}, "maxClinicalStage": s} for c, n, s in drugs]
    return httpx.Response(
        200,
        json={
            "data": {
                "disease": {
                    "id": DISEASE,
                    "drugAndClinicalCandidates": {"count": len(rows), "rows": rows},
                }
            }
        },
    )


class TestPipeline:
    def test_group_pipeline_orders_dedupes_and_counts(self) -> None:
        rows = [
            {"drug": {"id": "CHEMBL1", "name": "A"}, "maxClinicalStage": "PHASE_2"},
            {"drug": {"id": "CHEMBL1", "name": "A"}, "maxClinicalStage": "PHASE_2"},  # a dup
            {"drug": {"id": "CHEMBL2", "name": "B"}, "maxClinicalStage": "APPROVAL"},
            {"drug": {"id": "CHEMBL3", "name": "C"}, "maxClinicalStage": "PHASE_2"},
        ]
        pipe = enrich_cancer._group_pipeline(rows)
        # Most advanced first: APPROVAL leads PHASE_2.
        assert [g["stage"] for g in pipe["by_phase"]] == ["APPROVAL", "PHASE_2"]
        p2 = next(g for g in pipe["by_phase"] if g["stage"] == "PHASE_2")
        assert p2["count"] == 2  # CHEMBL1 deduped within the stage, plus CHEMBL3
        assert {d["chembl_id"] for d in p2["drugs"]} == {"CHEMBL1", "CHEMBL3"}
        assert pipe["total"] == 3

    def test_group_pipeline_empty_is_empty_dict(self) -> None:
        # An empty dict is what fact() classifies as EMPTY ("resolved, no programmes").
        assert enrich_cancer._group_pipeline([]) == {}

    @respx.mock
    async def test_pipeline_source_produces_a_stage_grouped_fact(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        respx.post(OT).mock(
            return_value=_pipeline_response(
                ("CHEMBL_A", "A", "APPROVAL"), ("CHEMBL_B", "B", "PHASE_2")
            )
        )
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_pipeline(fast_client, cancer)
        pf = record.facts["pipeline"]
        assert pf.status is FactStatus.OK
        assert pf.source == "opentargets"
        val = cast(dict[str, Any], pf.value)
        assert val["total"] == 2
        assert [g["stage"] for g in val["by_phase"]] == ["APPROVAL", "PHASE_2"]

    @respx.mock
    async def test_pipeline_outage_is_source_failed_not_empty(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        respx.post(OT).mock(
            return_value=httpx.Response(200, json={"errors": [{"message": "boom"}]})
        )
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_pipeline(fast_client, cancer)
        assert record.facts["pipeline"].status is FactStatus.SOURCE_FAILED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
