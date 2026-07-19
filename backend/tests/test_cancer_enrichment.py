"""Lazy cancer enrichment: the disease-side full loop and its honest states.

Mirrors test_lazy_enrichment.py. The full-loop test runs the real
get_or_start_cancer_brief on an unseeded database with the background session pointed at
the test DB and only the Open Targets HTTP mocked -- so a wiring break (a source that
never saves, an outage stored as "no targets") fails it rather than passing quietly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
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
CTGOV = "https://clinicaltrials.gov/api/v2/studies"
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


def _mock_ctgov(*, total: int, dach: int = 0, scanned: int = 3) -> None:
    """Mock the trial-reality source's two CT.gov calls: the DACH sub-query (RECRUITING filter)
    and the main condition page (a true totalCount + a small page of studies). With total=0 the
    source returns EMPTY before the DACH call, so only the main call fires."""
    studies = [
        {
            "protocolSection": {
                "statusModule": {"overallStatus": "RECRUITING"},
                "designModule": {"phases": ["PHASE2"]},
            }
        }
        for _ in range(scanned)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if dict(request.url.params).get("filter.overallStatus") == "RECRUITING":
            return httpx.Response(200, json={"totalCount": dach})
        return httpx.Response(200, json={"totalCount": total, "studies": studies})

    respx.get(CTGOV).mock(side_effect=handler)


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
            landscape = cast(dict[str, Any], tl.value)
            # The value carries the strong-association count and the threshold beside the
            # displayed targets -- the number is never stored without what it counts.
            assert landscape["threshold"] == enrich_cancer._STRONG_SCORE
            # All three mock scores (0.9, 0.8, 0.7) clear the 0.5 threshold.
            assert landscape["n_strong"] == 3
            targets = cast(list[dict[str, Any]], landscape["targets"])
            assert [t["symbol"] for t in targets] == ["EGFR", "KRAS", "ALK"]
            # Tractability and evidence channels made it through the mapping.
            assert targets[0]["sm_tractable"] is True
            assert targets[0]["ab_tractable"] is False
            assert "clinical" in targets[0]["evidence_types"]

            cancer = await fresh.get(Cancer, DISEASE)
            assert cancer is not None
            # Stamped: the next reader gets it from Postgres, not from Open Targets.
            assert cancer.last_enriched_at is not None

    @respx.mock
    async def test_opening_a_never_enriched_cancer_produces_trial_reality(
        self, session: AsyncSession, catalogued: None, db_engine: AsyncEngine
    ) -> None:
        """The trial-reality block arrives through the same lazy loop: the TRUE count (not the
        scanned page) and the query-side DACH count land as an OK trial_reality fact."""
        respx.post(OT).mock(return_value=_landscape_response("EGFR"))
        _mock_ctgov(total=8442, dach=122, scanned=3)
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        await get_or_start_cancer_brief(session, DISEASE, maker=maker)
        await cancer_briefs._in_flight[DISEASE]

        async with maker() as fresh:
            rows = await CancerRepository(fresh).facts_for(DISEASE)
            tr = {r.key: r for r in rows}.get("trial_reality")
            assert tr is not None, "the trial-reality source never saved"
            assert tr.source == "clinicaltrials"
            assert tr.status is FactStatus.OK
            assert tr.source_url and "clinicaltrials.gov" in tr.source_url
            value = cast(dict[str, Any], tr.value)
            # The count is the TRUE total, never the scanned page -- the "383 shown as 100" guard.
            assert value["n_trials"] == 8442
            assert value["n_trials_scanned"] == 3
            assert value["dach_recruiting"] == 122

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
        _mock_ctgov(total=0)  # one CT.gov call (EMPTY), so the per-enrich count is deterministic
        maker = async_sessionmaker(db_engine, expire_on_commit=False)

        states = await asyncio.gather(
            *(get_or_start_cancer_brief(session, DISEASE, maker=maker) for _ in range(5))
        )
        assert all(s is BriefState.ENRICHING for s in states)
        assert len(cancer_briefs._in_flight) == 1
        await cancer_briefs._in_flight[DISEASE]
        # The dedup that matters: ONE enrich, not five. One enrich makes exactly four external
        # calls here: three to OT (landscape and pipeline directly; epidemiology and survival
        # SHARE one ancestors fetch via the per-run cache, then both resolve UNMAPPED against the
        # unloaded disease map, so neither reaches Eurostat/SEER) and one to CT.gov (the trial-
        # reality condition query; total=0 returns EMPTY before the DACH sub-query). Five
        # enrichments would make five times this. (The in-flight dict length alone cannot catch a
        # broken dedup -- five tasks under the same key still leave len == 1.)
        assert respx.calls.call_count == 4

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
    rows = [
        {
            "maxClinicalStage": s,
            "drug": {
                "id": c,
                "name": n,
                "drugType": "Small molecule",
                "mechanismsOfAction": {"rows": []},
            },
        }
        for c, n, s in drugs
    ]
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
            # CHEMBL1's less-advanced row arrives FIRST; the more-advanced PHASE_2 row
            # (carrying the modality/mechanism) arrives SECOND -- Open Targets does not
            # guarantee order, so a first-seen-wins regression would keep the wrong stage,
            # and these assertions catch it.
            {"drug": {"id": "CHEMBL1", "name": "A"}, "maxClinicalStage": "PHASE_1"},
            {
                "drug": {
                    "id": "CHEMBL1",
                    "name": "A",
                    "drugType": "Small molecule",
                    "mechanismsOfAction": {"rows": [{"mechanismOfAction": "EGFR inhibitor"}]},
                },
                "maxClinicalStage": "PHASE_2",
            },
            {"drug": {"id": "CHEMBL2", "name": "B"}, "maxClinicalStage": "APPROVAL"},
            {"drug": {"id": "CHEMBL3", "name": "C"}, "maxClinicalStage": "PHASE_2"},
        ]
        pipe = enrich_cancer._group_pipeline(rows)
        # Distribution, most advanced first.
        assert [g["stage"] for g in pipe["by_phase"]] == ["APPROVAL", "PHASE_2"]
        assert {g["stage"]: g["count"] for g in pipe["by_phase"]} == {"APPROVAL": 1, "PHASE_2": 2}
        assert pipe["total"] == 3
        # Flat table, deduped by drug keeping the MORE advanced stage (CHEMBL1 -> PHASE_2,
        # not the later PHASE_1 row), sorted advanced-first then by name.
        drugs = {d["chembl_id"]: d for d in pipe["drugs"]}
        assert set(drugs) == {"CHEMBL1", "CHEMBL2", "CHEMBL3"}
        assert drugs["CHEMBL1"]["stage"] == "PHASE_2"
        assert drugs["CHEMBL1"]["modality"] == "Small molecule"
        assert drugs["CHEMBL1"]["mechanism"] == "EGFR inhibitor"
        # Missing modality/mechanism -> null, never a guess.
        assert drugs["CHEMBL2"]["modality"] is None
        assert drugs["CHEMBL2"]["mechanism"] is None
        # Table order: APPROVAL (B) first, then PHASE_2 (A, C by name).
        assert [d["chembl_id"] for d in pipe["drugs"]] == ["CHEMBL2", "CHEMBL1", "CHEMBL3"]

    def test_group_pipeline_empty_is_empty_dict(self) -> None:
        # An empty dict is what fact() classifies as EMPTY ("resolved, no programmes").
        assert enrich_cancer._group_pipeline([]) == {}

    def test_group_pipeline_survives_null_mechanism_rows(self) -> None:
        # Open Targets returns mechanismsOfAction.rows as JSON null (not absent) for some
        # drugs. That must not crash the source out uncaught -- it becomes an honest null
        # mechanism, so the outage-vs-empty guarantee still holds.
        rows = [
            {
                "drug": {
                    "id": "C1",
                    "name": "A",
                    "drugType": "Small molecule",
                    "mechanismsOfAction": {"rows": None},
                },
                "maxClinicalStage": "PHASE_2",
            },
        ]
        pipe = enrich_cancer._group_pipeline(rows)
        assert pipe["drugs"][0]["mechanism"] is None

    def test_group_pipeline_ranks_preapproval_as_advanced_not_bottom(self) -> None:
        # PREAPPROVAL (submitted, awaiting approval) is a real, advanced Open Targets
        # stage -- it must rank above earlier phases, not fall into the unknown tail. A
        # genuinely unknown stage does stay at the end.
        rows = [
            {"drug": {"id": "C1", "name": "A"}, "maxClinicalStage": "PHASE_1"},
            {"drug": {"id": "C2", "name": "B"}, "maxClinicalStage": "PREAPPROVAL"},
            {"drug": {"id": "C3", "name": "C"}, "maxClinicalStage": "MADE_UP_STAGE"},
        ]
        stages = [g["stage"] for g in enrich_cancer._group_pipeline(rows)["by_phase"]]
        assert stages == ["PREAPPROVAL", "PHASE_1", "MADE_UP_STAGE"]

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


def _scored_landscape(scores: list[float]) -> httpx.Response:
    """A target-landscape answer with one target (T0, T1, ...) per given score."""
    rows = [
        {
            "score": s,
            "datatypeScores": [{"id": "clinical", "score": s}],
            "target": {"approvedSymbol": f"T{i}", "tractability": []},
        }
        for i, s in enumerate(scores)
    ]
    return httpx.Response(
        200,
        json={
            "data": {
                "disease": {"id": DISEASE, "associatedTargets": {"count": len(rows), "rows": rows}}
            }
        },
    )


class TestTargetLandscape:
    """The strong-association metric: the whole point of R3 is that the headline count is
    the strong set, above a documented threshold, never the ~12,000-with-any-evidence total
    that reads as 'the whole genome'. These go red if the threshold is dropped."""

    @respx.mock
    async def test_n_strong_counts_only_scores_at_or_above_the_threshold(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        # Five targets, three at/above 0.5 (0.9, 0.5, 0.6), two below (0.4, 0.1). n_strong
        # must be 3, not 5 -- 0.5 itself is strong (>=). Drop the threshold filter and this
        # reads 5, which is exactly the misleading whole-genome count R3 exists to kill.
        respx.post(OT).mock(return_value=_scored_landscape([0.9, 0.5, 0.6, 0.4, 0.1]))
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_target_landscape(fast_client, cancer)
        val = cast(dict[str, Any], record.facts["target_landscape"].value)
        assert val["n_strong"] == 3
        # The threshold travels with the count -- the number is never stored bare.
        assert val["threshold"] == enrich_cancer._STRONG_SCORE

    @respx.mock
    async def test_n_strong_counts_the_whole_page_not_just_the_displayed_top(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        # More strong targets than the display cap: the count is over the full scanned page,
        # the displayed list is capped at _TOP_TARGETS. Counting only the shown rows would
        # undercount the headline metric.
        n = enrich_cancer._TOP_TARGETS + 10
        respx.post(OT).mock(return_value=_scored_landscape([0.8] * n))
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_target_landscape(fast_client, cancer)
        val = cast(dict[str, Any], record.facts["target_landscape"].value)
        assert val["n_strong"] == n
        assert len(val["targets"]) == enrich_cancer._TOP_TARGETS

    @respx.mock
    async def test_n_strong_excludes_strong_rows_without_an_approved_symbol(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        # A strong (>= 0.5) association whose target has no approvedSymbol must NOT be
        # counted: the card needs a symbol to render a target, so counting it would let the
        # headline ("2 strong") contradict the card ("no associated targets"). The count and
        # the displayed list share one approvedSymbol basis.
        rows = [
            {"score": 0.9, "target": {"approvedSymbol": "EGFR"}},
            {"score": 0.8, "target": {"approvedSymbol": None}},
        ]
        respx.post(OT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "disease": {
                            "id": DISEASE,
                            "associatedTargets": {"count": 2, "rows": rows},
                        }
                    }
                },
            )
        )
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_target_landscape(fast_client, cancer)
        val = cast(dict[str, Any], record.facts["target_landscape"].value)
        # Only the symboled strong row counts, and it is the only displayed target.
        assert val["n_strong"] == 1
        assert [t["symbol"] for t in val["targets"]] == ["EGFR"]

    @respx.mock
    async def test_a_resolved_disease_with_no_targets_is_empty_not_ok(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        # Resolved, zero associations -> a measured EMPTY, distinct from the outage and
        # not-found cases. The dict wrapper must not turn an empty landscape into an OK fact.
        respx.post(OT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "disease": {
                            "id": DISEASE,
                            "associatedTargets": {"count": 0, "rows": []},
                        }
                    }
                },
            )
        )
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_target_landscape(fast_client, cancer)
        assert record.facts["target_landscape"].status is FactStatus.EMPTY


def _landscape_with_ids(targets: list[tuple[str, str, float]]) -> httpx.Response:
    """A landscape answer whose targets carry Ensembl ids: (symbol, ensembl_id, score)."""
    rows = [
        {
            "score": s,
            "datatypeScores": [],
            "target": {"id": eid, "approvedSymbol": sym, "tractability": []},
        }
        for sym, eid, s in targets
    ]
    return httpx.Response(
        200,
        json={
            "data": {
                "disease": {"id": DISEASE, "associatedTargets": {"count": len(rows), "rows": rows}}
            }
        },
    )


def _drug_status_response(by_id: dict[str, list[str]]) -> httpx.Response:
    """A targets() drug-status answer. by_id maps Ensembl id -> its maxClinicalStages;
    an empty list means 'resolved, no drugs'; an id absent from by_id is 'not resolved'."""
    targets = [
        {
            "id": eid,
            "drugAndClinicalCandidates": {
                "count": len(stages),
                "rows": [{"maxClinicalStage": st} for st in stages],
            },
        }
        for eid, stages in by_id.items()
    ]
    return httpx.Response(200, json={"data": {"targets": targets}})


def _ot_router(
    landscape: httpx.Response, drug_status: httpx.Response
) -> Callable[[httpx.Request], httpx.Response]:
    """Route the two OT POSTs (both to the same endpoint) by which query they carry."""

    def route(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if "TargetDrugStatus" in body or "ensemblIds" in body:
            return drug_status
        return landscape

    return route


class TestDrugStatus:
    """R4: the drugged/in-development/unexploited flag. The load-bearing rule is that a
    target OT never resolved reads 'unknown', never 'unexploited' -- absence of a
    measurement is not a measurement of absence, in the highest-stakes cell on the page."""

    def test_classify_approved_from_approval_or_phase4(self) -> None:
        assert (
            enrich_cancer._classify_drug_status({"rows": [{"maxClinicalStage": "APPROVAL"}]})
            == "approved"
        )
        # PHASE_4 is post-marketing -> only reached after approval, so it counts as approved.
        two = {"rows": [{"maxClinicalStage": "PHASE_4"}, {"maxClinicalStage": "PHASE_2"}]}
        assert enrich_cancer._classify_drug_status(two) == "approved"

    def test_classify_clinical_when_candidates_but_none_approved(self) -> None:
        rows = {"rows": [{"maxClinicalStage": "PHASE_3"}, {"maxClinicalStage": "PHASE_2"}]}
        assert enrich_cancer._classify_drug_status(rows) == "clinical"

    def test_classify_unexploited_only_when_resolved_and_no_rows(self) -> None:
        assert enrich_cancer._classify_drug_status({"rows": []}) == "unexploited"
        assert enrich_cancer._classify_drug_status({"count": 0, "rows": None}) == "unexploited"
        assert enrich_cancer._classify_drug_status(None) == "unexploited"

    @respx.mock
    async def test_fetch_maps_by_id_not_position(self, fast_client: httpx.AsyncClient) -> None:
        # Response order reversed vs the request -> the mapping must follow the echoed id,
        # not the position, or a status lands on the wrong target.
        respx.post(OT).mock(
            return_value=_drug_status_response({"ENSG_B": ["PHASE_2"], "ENSG_A": ["APPROVAL"]})
        )
        out = await enrich_cancer._fetch_drug_status(fast_client, ["ENSG_A", "ENSG_B"])
        assert out == {"ENSG_A": "approved", "ENSG_B": "clinical"}

    @respx.mock
    async def test_fetch_total_failure_returns_empty(self, fast_client: httpx.AsyncClient) -> None:
        respx.post(OT).mock(
            return_value=httpx.Response(200, json={"errors": [{"message": "boom"}]})
        )
        assert await enrich_cancer._fetch_drug_status(fast_client, ["ENSG_A"]) == {}

    @respx.mock
    async def test_landscape_attaches_the_three_states(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        landscape = _landscape_with_ids(
            [("EGFR", "ENSG_E", 0.9), ("TP53", "ENSG_T", 0.8), ("STK11", "ENSG_S", 0.7)]
        )
        drugs = _drug_status_response({"ENSG_E": ["APPROVAL"], "ENSG_T": ["PHASE_2"], "ENSG_S": []})
        respx.post(OT).mock(side_effect=_ot_router(landscape, drugs))
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_target_landscape(fast_client, cancer)
        val = cast(dict[str, Any], record.facts["target_landscape"].value)
        by_sym = {t["symbol"]: t["drug_status"] for t in val["targets"]}
        assert by_sym == {"EGFR": "approved", "TP53": "clinical", "STK11": "unexploited"}
        # The Ensembl id is carried for the catalog join (R4-2), never the symbol.
        assert {t["symbol"]: t["ensembl_id"] for t in val["targets"]}["EGFR"] == "ENSG_E"

    @respx.mock
    async def test_drug_status_outage_leaves_unknown_never_unexploited(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        # The landscape resolves, but the drug-status batch is down. Every target must read
        # 'unknown', NOT 'unexploited' -- an outage is not "the world has no drug for this".
        landscape = _landscape_with_ids([("EGFR", "ENSG_E", 0.9)])
        failed_drugs = httpx.Response(200, json={"errors": [{"message": "drug status down"}]})
        respx.post(OT).mock(side_effect=_ot_router(landscape, failed_drugs))
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_target_landscape(fast_client, cancer)
        val = cast(dict[str, Any], record.facts["target_landscape"].value)
        statuses = [t["drug_status"] for t in val["targets"]]
        assert statuses == ["unknown"]
        assert "unexploited" not in statuses
        # The landscape itself still stands -- a down flag sub-query is not a down landscape.
        assert record.facts["target_landscape"].status is FactStatus.OK

    @respx.mock
    async def test_partial_batch_marks_only_the_missing_unknown(
        self, fast_client: httpx.AsyncClient
    ) -> None:
        # Two targets, the batch resolves only one. The resolved one keeps its real status;
        # the unresolved one is 'unknown', NOT 'unexploited', and does not contaminate the
        # resolved one.
        landscape = _landscape_with_ids([("EGFR", "ENSG_E", 0.9), ("MYSTERY", "ENSG_M", 0.8)])
        drugs = _drug_status_response({"ENSG_E": ["APPROVAL"]})  # ENSG_M omitted = unresolved
        respx.post(OT).mock(side_effect=_ot_router(landscape, drugs))
        cancer = Cancer(disease_id=DISEASE, name="NSCLC", n_drugs=0, n_targets=0)
        record = await enrich_cancer.opentargets_target_landscape(fast_client, cancer)
        val = cast(dict[str, Any], record.facts["target_landscape"].value)
        by_sym = {t["symbol"]: t["drug_status"] for t in val["targets"]}
        assert by_sym == {"EGFR": "approved", "MYSTERY": "unknown"}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
