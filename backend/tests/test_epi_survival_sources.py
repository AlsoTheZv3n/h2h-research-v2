"""The epidemiology + survival CancerSources: the honest-state mapping from a disease-map
resolution to a fact. resolve() is proven in test_disease_resolution; here we prove the SOURCE
turns each outcome into the right fact -- exact/rollup carry the named entity, unmapped is its
own OK state (never empty/source_failed), an outage is amber, a resolved-but-empty is EMPTY."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from backend.ingestion import eurostat, seer
from backend.ingestion.base import FactStatus
from backend.ingestion.enrich_cancer import make_epidemiology_source, make_survival_source
from backend.models import Cancer

OT = "https://api.platform.opentargets.org/api/v4/graphql"
CANCER = Cancer(disease_id="MONDO_0005233")


def _ancestors(*ids: str) -> httpx.Response:
    return httpx.Response(
        200, json={"data": {"disease": {"id": CANCER.disease_id, "ancestors": list(ids)}}}
    )


def _stub(monkeypatch: pytest.MonkeyPatch, source: str, fn: Any) -> None:
    # Patch the adapter on its own module -- the same object the enrich_cancer closures call.
    if source == "eurostat":
        monkeypatch.setattr(eurostat, "fetch_epidemiology", fn)
    else:
        monkeypatch.setattr(seer, "fetch_survival", fn)


async def _run_epi(source_map: dict[str, tuple[str, str]]) -> Any:
    async with httpx.AsyncClient() as client:
        rec = await make_epidemiology_source(source_map, {})(client, CANCER)
    return rec.facts["epidemiology"]


async def _run_survival(source_map: dict[str, tuple[str, str]]) -> Any:
    async with httpx.AsyncClient() as client:
        rec = await make_survival_source(source_map, {})(client, CANCER)
    return rec.facts["survival"]


class TestEpidemiologySource:
    async def test_exact_carries_the_data_and_match_type(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def data(_c: Any, code: str) -> dict[str, Any]:
            return {"year": 2023, "eu_asr": 17.07, "by_country": [{"geo": "CH", "asr": 13.97}]}

        _stub(monkeypatch, "eurostat", data)
        # The cancer IS the mapped category -> exact, and no ancestors are fetched (no OT call).
        f = await _run_epi({CANCER.disease_id: ("C50", "Breast (C50)")})
        assert f.status is FactStatus.OK
        assert f.value["match_type"] == "exact"
        assert f.value["source_label"] == "Breast (C50)"
        assert f.value["year"] == 2023

    @respx.mock
    async def test_rollup_names_the_broader_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        respx.post(OT).mock(return_value=_ancestors("MONDO_LUNG", "MONDO_ROOT"))

        async def data(_c: Any, code: str) -> dict[str, Any]:
            return {"year": 2023, "eu_asr": 46.65}

        _stub(monkeypatch, "eurostat", data)
        # NSCLC rolls up to lung: the value MUST name lung so its figures are never passed off
        # as NSCLC's own -- the whole reason the mapping carries match_type + the target label.
        f = await _run_epi({"MONDO_LUNG": ("C33_C34", "Trachea, bronchus & lung (C33-C34)")})
        assert f.value["match_type"] == "rollup"
        assert f.value["target_mondo"] == "MONDO_LUNG"
        assert "lung" in f.value["source_label"].lower()

    @respx.mock
    async def test_unmapped_is_its_own_ok_state(self) -> None:
        respx.post(OT).mock(return_value=_ancestors("MONDO_ROOT"))
        # No European category applies. An OK fact whose value says only "unmapped" -- kept
        # distinct from empty (source had nothing) and source_failed (an outage).
        f = await _run_epi({"MONDO_UNRELATED": ("C50", "Breast")})
        assert f.status is FactStatus.OK
        assert f.value == {"match_type": "unmapped"}

    async def test_a_source_outage_is_amber_not_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(_c: Any, code: str) -> dict[str, Any]:
            raise httpx.ConnectError("eurostat down")

        _stub(monkeypatch, "eurostat", boom)
        f = await _run_epi({CANCER.disease_id: ("C50", "Breast")})
        # An outage after a successful resolve is source_failed (amber), never a fabricated
        # "no deaths".
        assert f.status is FactStatus.SOURCE_FAILED
        assert f.value is None

    async def test_resolved_but_no_data_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def none(_c: Any, code: str) -> None:
            return None

        _stub(monkeypatch, "eurostat", none)
        f = await _run_epi({CANCER.disease_id: ("C50", "Breast")})
        assert f.status is FactStatus.EMPTY

    @respx.mock
    async def test_a_resolution_outage_is_source_failed(self) -> None:
        respx.post(OT).mock(return_value=httpx.Response(500))
        # Open Targets is down, so we cannot even resolve the cancer -> amber, never a silent
        # "not available for this cancer" (which would read as a settled answer).
        f = await _run_epi({"MONDO_UNRELATED": ("C50", "Breast")})
        assert f.status is FactStatus.SOURCE_FAILED

    @respx.mock
    async def test_an_unresolvable_disease_id_is_skipped_not_unmapped(self) -> None:
        # OT answers but does not resolve the id (drift/deprecation). That is a lookup miss, not
        # "not available for this cancer": no fact is written (the same skip landscape/pipeline
        # make), so the card reads "not collected", never a false settled UNMAPPED.
        respx.post(OT).mock(return_value=httpx.Response(200, json={"data": {"disease": None}}))
        async with httpx.AsyncClient() as client:
            rec = await make_epidemiology_source({"MONDO_UNRELATED": ("C50", "Breast")}, {})(
                client, CANCER
            )
        assert "epidemiology" not in rec.facts
        assert rec.error is not None and "did not resolve" in rec.error

    @respx.mock
    async def test_shared_cache_fetches_the_cancer_ancestors_once_across_both_sources(self) -> None:
        route = respx.post(OT).mock(return_value=_ancestors("MONDO_ROOT"))
        cache: dict[str, list[str]] = {}
        async with httpx.AsyncClient() as client:
            await make_epidemiology_source({"MONDO_OTHER": ("C50", "Breast")}, cache)(
                client, CANCER
            )
            await make_survival_source({"MONDO_OTHER": ("47", "Lung")}, cache)(client, CANCER)
        # Both sources resolved the same cancer against different maps, but its ancestors were
        # fetched from Open Targets ONCE -- the shared cache absorbs the second lookup.
        assert route.call_count == 1


class TestSurvivalSource:
    @respx.mock
    async def test_rollup_names_the_broader_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        respx.post(OT).mock(return_value=_ancestors("MONDO_LUNG", "MONDO_ROOT"))

        async def data(_c: Any, site: int) -> dict[str, Any]:
            return {"metric": "5-year relative survival", "staged": True, "by_stage": []}

        _stub(monkeypatch, "seer", data)
        f = await _run_survival({"MONDO_LUNG": ("47", "Lung and Bronchus")})
        assert f.value["match_type"] == "rollup"
        assert "lung" in f.value["source_label"].lower()
        assert f.value["metric"] == "5-year relative survival"

    @respx.mock
    async def test_unmapped_is_its_own_ok_state(self) -> None:
        respx.post(OT).mock(return_value=_ancestors("MONDO_ROOT"))
        f = await _run_survival({"MONDO_UNRELATED": ("47", "Lung")})
        assert f.status is FactStatus.OK
        assert f.value == {"match_type": "unmapped"}
