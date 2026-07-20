"""Observed combinations: classify a drug's multi-drug trials from ARM structure.

The load-bearing distinction is combination (A+B, one arm) vs comparison (A vs B, two arms) --
opposite meanings that only the arm structure separates, never name co-occurrence. And the
multi-drug trials with no arm-level drug assignment are AMBIGUOUS and dropped, never guessed.
These tests pin the classifier against crafted arm modules and the adapter against a mocked
ClinicalTrials.gov (OK with counts + examples, a measured EMPTY, and an outage -> source_failed).
"""

from __future__ import annotations

from typing import Any

import httpx
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import FactStatus
from backend.ingestion.clinicaltrials_combinations import (
    BASE,
    ClinicalTrialsCombinationsAdapter,
    _classify,
)
from backend.ingestion.enrich import EnrichStats, _save_source_record
from backend.models import DataMaturity
from backend.repositories import DrugRepository


def _mod(interventions: list[dict[str, Any]], arms: list[dict[str, Any]]) -> dict[str, Any]:
    return {"interventions": interventions, "armGroups": arms}


def _iv(name: str, itype: str = "DRUG") -> dict[str, Any]:
    return {"type": itype, "name": name}


def _arm(*names: str) -> dict[str, Any]:
    return {"interventionNames": list(names)}


class TestClassify:
    def test_a_single_arm_with_two_drugs_is_a_combination(self) -> None:
        c = _classify(_mod([_iv("A"), _iv("B")], [_arm("A", "B")]))
        assert c.kind == "combination"
        assert c.drugs == ["A", "B"]  # the partners, sorted

    def test_two_arms_of_different_single_drugs_is_a_comparison(self) -> None:
        c = _classify(_mod([_iv("A"), _iv("B")], [_arm("A"), _arm("B")]))
        assert c.kind == "comparison"
        assert c.drugs == ["A", "B"]

    def test_combination_wins_ties_over_comparison(self) -> None:
        # A GENUINE tie: the trial has a combo arm (A+B) AND >=2 distinct single-drug arms (C, D),
        # so it independently qualifies as BOTH a combination and a comparison. Combination wins --
        # the spike's rule. Reversing the precedence in _classify returns comparison [C, D] and
        # reddens this (the earlier one-single-arm fixture could not, since it was no real tie).
        c = _classify(
            _mod([_iv("A"), _iv("B"), _iv("C"), _iv("D")], [_arm("A", "B"), _arm("C"), _arm("D")])
        )
        assert c.kind == "combination"
        assert c.drugs == ["A", "B"]

    def test_multi_drug_with_no_arm_assignment_is_ambiguous(self) -> None:
        # Two drugs named on the trial, but no arm names a drug -> cannot tell A+B from A vs B.
        assert _classify(_mod([_iv("A"), _iv("B")], [])).kind == "ambiguous"

    def test_same_drug_across_two_arms_is_ambiguous_not_a_comparison(self) -> None:
        # Two DISTINCT drugs are named (passes the multi-drug gate), but the arms name the SAME
        # single drug (dose arms of A); B is assigned to no arm. Fewer than 2 DISTINCT single
        # drugs -> not an A-vs-B comparison -> ambiguous (dropped), the second ambiguous branch.
        # Counting arms instead of distinct drug names would wrongly call this A vs A.
        assert _classify(_mod([_iv("A"), _iv("B")], [_arm("A"), _arm("A")])).kind == "ambiguous"

    def test_one_drug_is_single_drug(self) -> None:
        assert _classify(_mod([_iv("A")], [_arm("A")])).kind == "single-drug"

    def test_placebo_and_non_drug_arms_do_not_count_as_a_second_drug(self) -> None:
        # A drug vs placebo is a single-drug trial, not a comparison of two drugs.
        assert _classify(_mod([_iv("A"), _iv("Placebo")], [_arm("A"), _arm("Placebo")])).kind == (
            "single-drug"
        )

    def test_non_drug_intervention_types_are_ignored(self) -> None:
        # A DRUG plus a PROCEDURE is not two drugs.
        c = _classify(_mod([_iv("A"), _iv("Surgery", itype="PROCEDURE")], [_arm("A")]))
        assert c.kind == "single-drug"


def _study(
    nct: str, interventions: list[dict[str, Any]], arms: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct},
            "armsInterventionsModule": {"interventions": interventions, "armGroups": arms},
        }
    }


def _response(
    studies: list[dict[str, Any]], total: int, token: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"studies": studies, "totalCount": total}
    if token:
        body["nextPageToken"] = token
    return body


@respx.mock
async def test_fetch_classifies_and_carries_examples_and_true_total(
    fast_client: httpx.AsyncClient,
) -> None:
    studies = [
        _study("NCT_COMBO", [_iv("focus"), _iv("partner")], [_arm("focus", "partner")]),
        _study("NCT_COMPARE", [_iv("focus"), _iv("rival")], [_arm("focus"), _arm("rival")]),
        _study("NCT_AMBIG", [_iv("focus"), _iv("other")], []),  # dropped
        _study("NCT_SINGLE", [_iv("focus")], [_arm("focus")]),  # excluded (not multi-drug)
    ]
    # totalCount is far above the 4 scanned -> the scanned-vs-total honesty is exercised.
    respx.get(BASE).mock(return_value=httpx.Response(200, json=_response(studies, total=999)))

    rec = await ClinicalTrialsCombinationsAdapter(fast_client).fetch("focus")
    f = rec.facts["combinations"]
    assert f.status is FactStatus.OK
    v = f.value
    assert isinstance(v, dict)
    assert v["n_total"] == 999
    assert v["n_scanned"] == 4
    assert v["n_combination"] == 1
    assert v["n_comparison"] == 1
    assert v["n_ambiguous"] == 1  # the ambiguous trial is counted (for honesty) but not classified
    assert v["n_multi_drug"] == 3  # combination + comparison + ambiguous; single-drug excluded
    assert v["combination_examples"][0]["nct_id"] == "NCT_COMBO"
    assert v["combination_examples"][0]["drugs"] == ["focus", "partner"]
    assert v["comparison_examples"][0]["nct_id"] == "NCT_COMPARE"


@respx.mock
async def test_fetch_with_no_classifiable_trials_is_a_measured_empty(
    fast_client: httpx.AsyncClient,
) -> None:
    # Only single-drug and ambiguous trials -> nothing we can stand behind -> EMPTY, not OK-with-
    # zeros and not an outage.
    studies = [
        _study("NCT_SINGLE", [_iv("focus")], [_arm("focus")]),
        _study("NCT_AMBIG", [_iv("focus"), _iv("other")], []),
    ]
    respx.get(BASE).mock(return_value=httpx.Response(200, json=_response(studies, total=2)))

    rec = await ClinicalTrialsCombinationsAdapter(fast_client).fetch("focus")
    assert rec.facts["combinations"].status is FactStatus.EMPTY


@respx.mock
async def test_fetch_paginates_and_reports_scanned_count(fast_client: httpx.AsyncClient) -> None:
    page1 = _response(
        [_study("NCT1", [_iv("a"), _iv("b")], [_arm("a", "b")])], total=2, token="TOK"
    )
    page2 = _response([_study("NCT2", [_iv("a"), _iv("c")], [_arm("a"), _arm("c")])], total=2)

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pageToken")
        return httpx.Response(200, json=page2 if token == "TOK" else page1)

    respx.get(BASE).mock(side_effect=handler)

    rec = await ClinicalTrialsCombinationsAdapter(fast_client).fetch("a")
    v = rec.facts["combinations"].value
    assert isinstance(v, dict)
    assert v["n_scanned"] == 2  # both pages followed
    assert v["n_combination"] == 1
    assert v["n_comparison"] == 1


@respx.mock
async def test_fetch_on_outage_is_source_failed_never_no_combinations(
    fast_client: httpx.AsyncClient,
) -> None:
    respx.get(BASE).mock(return_value=httpx.Response(500, text="upstream is down"))
    rec = await ClinicalTrialsCombinationsAdapter(fast_client).fetch("focus")
    # An outage: the resolve failed, so no facts and outage=True -> _save_source_record
    # synthesises a source_failed `combinations` fact. Never a measured "no combinations".
    assert rec.outage is True
    assert rec.facts == {}


@respx.mock
async def test_scan_stops_at_the_cap(fast_client: httpx.AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Every page carries a nextPageToken, so ONLY the scan cap can stop the loop -- if the cap
    # check or the out[:cap] truncation regressed, this would run forever (a hang, caught as a
    # failure) or over-count. With the cap at 3 and pages of 2, the loop fetches 2 pages (4) and
    # truncates to 3.
    import backend.ingestion.clinicaltrials_combinations as mod

    monkeypatch.setattr(mod, "_SCAN_CAP", 3)
    page = _response(
        [
            _study("NCTx", [_iv("a"), _iv("b")], [_arm("a", "b")]),
            _study("NCTy", [_iv("a"), _iv("b")], [_arm("a", "b")]),
        ],
        total=99,
        token="MORE",
    )
    respx.get(BASE).mock(return_value=httpx.Response(200, json=page))

    rec = await ClinicalTrialsCombinationsAdapter(fast_client).fetch("a")
    v = rec.facts["combinations"].value
    assert isinstance(v, dict)
    assert v["n_scanned"] == 3  # capped, not the 4 fetched or an unbounded scan


@respx.mock
async def test_an_outage_synthesises_a_persisted_source_failed_combinations_fact(
    session: AsyncSession, fast_client: httpx.AsyncClient
) -> None:
    # owned_keys=("combinations",) is what makes _save_source_record write a source_failed fact on
    # a CT.gov outage. Empty or mistype owned_keys and NO combinations fact is written -> the card
    # falls back to "Not collected" -- an outage rendered as an absence, this project's founding
    # bug. The fetch-level outage test checks only the SourceRecord flags; this pins the persisted
    # synthesis end to end.
    repo = DrugRepository(session)
    drug = await repo.upsert_drug("CHEMBL_CMB", pref_name="focus", maturity=DataMaturity.INDEX_ONLY)
    adapter = ClinicalTrialsCombinationsAdapter(fast_client)
    respx.get(BASE).mock(return_value=httpx.Response(500, text="down"))

    rec = await adapter.fetch("focus")
    await _save_source_record(repo, drug, adapter, rec, EnrichStats())
    await session.commit()

    facts = {f.key: f for f in await repo.facts_for("CHEMBL_CMB")}
    assert facts["combinations"].status is FactStatus.SOURCE_FAILED
