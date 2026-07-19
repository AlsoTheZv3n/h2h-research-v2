"""The ClinicalTrials.gov trial-reality source: the honest, decision-useful fact and its states.

Unit tests for ctgov_cancer.fetch_trial_reality and enrich_cancer.cancer_trial_reality. CT.gov is
mocked here; the live field verification is the P1-T4.0 gate (issue #20). The load-bearing guards
-- count-is-the-true-total-not-the-page, an outage is not "no trials", an absent count is unknown
not zero, a failed DACH sub-query is unknown not zero -- each fail when the code is broken.
"""

from __future__ import annotations

from typing import Any

import httpx
import respx

from backend.ingestion import ctgov_cancer
from backend.ingestion.base import FactStatus
from backend.ingestion.enrich_cancer import cancer_trial_reality
from backend.models import Cancer

CTGOV = ctgov_cancer.BASE
COND = "non-small cell lung carcinoma"


def _study(status: str, *, phase: str | None = None, why: str | None = None) -> dict[str, Any]:
    sm: dict[str, Any] = {"overallStatus": status}
    if why is not None:
        sm["whyStopped"] = why
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000000"},
            "statusModule": sm,
            "designModule": {"phases": [phase] if phase else []},
        }
    }


def _main(total: int | None, studies: list[dict[str, Any]]) -> httpx.Response:
    body: dict[str, Any] = {"studies": studies}
    if total is not None:
        body["totalCount"] = total
    return httpx.Response(200, json=body)


def _route(total: int | None, studies: list[dict[str, Any]], *, dach: int | None = 0) -> None:
    """Mock both CT.gov calls by inspecting the request: the DACH sub-query (RECRUITING filter)
    vs the main condition page. `dach=None` simulates a response carrying no count on that call."""

    def handler(request: httpx.Request) -> httpx.Response:
        if dict(request.url.params).get("filter.overallStatus") == "RECRUITING":
            return httpx.Response(200, json={} if dach is None else {"totalCount": dach})
        return _main(total, studies)

    respx.get(CTGOV).mock(side_effect=handler)


async def _fetch(cond: str = COND) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=10) as client:
        return await ctgov_cancer.fetch_trial_reality(client, cond)


class TestFetchTrialReality:
    @respx.mock
    async def test_n_trials_is_the_true_count_never_the_scanned_page(self) -> None:
        # The "osimertinib 383 shown as 100" guard: n_trials is countTotal, not len(studies).
        _route(8442, [_study("RECRUITING"), _study("COMPLETED"), _study("TERMINATED")], dach=122)
        data = await _fetch()
        assert data is not None
        assert data["n_trials"] == 8442
        assert data["n_trials_scanned"] == 3
        assert data["dach_recruiting"] == 122
        assert data["condition"] == COND

    @respx.mock
    async def test_distributions_and_stopped_reasons(self) -> None:
        _route(
            10,
            [
                _study("RECRUITING", phase="PHASE2"),
                _study("RECRUITING", phase="PHASE1"),
                _study("TERMINATED", phase="PHASE1", why="Slow accrual"),
                _study("WITHDRAWN", why="Slow accrual"),
                _study("SUSPENDED"),  # stopped, but no whyStopped -> counted, contributes no reason
            ],
        )
        data = await _fetch()
        assert data is not None
        assert {d["phase"]: d["count"] for d in data["by_phase"]} == {"PHASE1": 2, "PHASE2": 1}
        # RECRUITING leads the status order.
        assert data["by_status"][0] == {"status": "RECRUITING", "count": 2}
        # 3 stopped; one reason shared by 2, the reasonless SUSPENDED omitted (never invented).
        assert data["stopped"]["count"] == 3
        assert data["stopped"]["reasons"] == [{"reason": "Slow accrual", "count": 2}]

    @respx.mock
    async def test_zero_trials_returns_none_for_empty(self) -> None:
        _route(0, [])
        assert await _fetch() is None

    @respx.mock
    async def test_absent_total_count_is_unavailable_not_the_page_length(self) -> None:
        # The API returned a page but no countTotal: n_trials is None (count unavailable), NEVER
        # len(studies). Distributions over the page are kept.
        _route(None, [_study("RECRUITING"), _study("COMPLETED")])
        data = await _fetch()
        assert data is not None
        assert data["n_trials"] is None
        assert data["n_trials_scanned"] == 2
        assert data["by_status"]

    @respx.mock
    async def test_failed_dach_subquery_is_unknown_not_zero(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if dict(request.url.params).get("filter.overallStatus") == "RECRUITING":
                return httpx.Response(500)  # the DACH sub-query is down
            return _main(50, [_study("RECRUITING")])

        respx.get(CTGOV).mock(side_effect=handler)
        data = await _fetch()
        assert data is not None
        assert data["n_trials"] == 50
        assert data["dach_recruiting"] is None  # unknown, NEVER 0 recruiting

    @respx.mock
    async def test_a_real_zero_dach_is_zero_not_unknown(self) -> None:
        # A present count of 0 DACH-recruiting is a real measured zero, distinct from the failure
        # above -- so the two do not collapse.
        _route(50, [_study("RECRUITING")], dach=0)
        data = await _fetch()
        assert data is not None
        assert data["dach_recruiting"] == 0


def _cancer(name: str | None = COND) -> Cancer:
    return Cancer(
        disease_id="MONDO_0005233", name=name, therapeutic_area=None, n_drugs=0, n_targets=0
    )


async def _record(cancer: Cancer) -> Any:
    async with httpx.AsyncClient(timeout=10) as client:
        return await cancer_trial_reality(client, cancer)


class TestTrialRealitySource:
    @respx.mock
    async def test_an_outage_is_source_failed_not_no_trials(self) -> None:
        respx.get(CTGOV).mock(return_value=httpx.Response(503))
        rec = await _record(_cancer())
        f = rec.facts["trial_reality"]
        assert f.status is FactStatus.SOURCE_FAILED  # NOT empty
        assert f.value is None

    @respx.mock
    async def test_zero_trials_is_a_measured_empty(self) -> None:
        _route(0, [])
        rec = await _record(_cancer())
        f = rec.facts["trial_reality"]
        assert f.status is FactStatus.EMPTY
        assert f.value is None

    @respx.mock
    async def test_an_ok_fact_carries_the_value(self) -> None:
        _route(8442, [_study("RECRUITING")], dach=122)
        rec = await _record(_cancer())
        f = rec.facts["trial_reality"]
        assert f.status is FactStatus.OK
        assert f.value["n_trials"] == 8442
        assert f.source == "clinicaltrials"

    @respx.mock
    async def test_a_nameless_cancer_writes_no_fact(self) -> None:
        rec = await _record(_cancer(name=None))
        assert rec.facts == {}  # never a measured EMPTY for a cancer we could not query
        assert rec.error
