"""The Eurostat mortality adapter: pin the JSON-stat parsing so a structure change fails
loudly, and prove the honest shaping -- country-level only (no NUTS sub-regions), sorted by
ASR, the EU aggregate read separately, absolute deaths a single EU headline."""

from __future__ import annotations

from typing import Any

import httpx
import respx

from backend.ingestion.eurostat import API, fetch_epidemiology

# A minimal hlth_cd_asdr2 slice: one icd10, one year, five geographies -- the EU aggregate, two
# countries, and one NUTS-2 sub-region (BE21) that MUST be filtered out of the per-country bars.
# Dims are all size 1 except geo, so a category's flat index is just its geo position.
_ASDR2 = {
    "id": ["freq", "unit", "sex", "age", "icd10", "geo", "time"],
    "size": [1, 1, 1, 1, 1, 5, 1],
    "dimension": {
        "freq": {"category": {"index": {"A": 0}}},
        "unit": {"category": {"index": {"RT": 0}}},
        "sex": {"category": {"index": {"T": 0}}},
        "age": {"category": {"index": {"TOTAL": 0}}},
        "icd10": {"category": {"index": {"C33_C34": 0}}},
        "geo": {
            "category": {
                "index": {"EU27_2020": 0, "CH": 1, "DE": 2, "BE21": 3, "HU": 4},
                "label": {
                    "EU27_2020": "European Union - 27 countries (from 2020)",
                    "CH": "Switzerland",
                    "DE": "Germany",
                    "BE21": "Prov. Antwerpen",
                    "HU": "Hungary",
                },
            }
        },
        "time": {"category": {"index": {"2023": 0}}},
    },
    # geo positions: EU=0, CH=1, DE=2, BE21=3, HU=4
    "value": {"0": 46.65, "1": 34.77, "2": 40.0, "3": 99.9, "4": 80.07},
}

_ARO = {
    "id": ["freq", "unit", "sex", "age", "icd10", "resid", "geo", "time"],
    "size": [1, 1, 1, 1, 1, 1, 1, 1],
    "dimension": {
        "freq": {"category": {"index": {"A": 0}}},
        "unit": {"category": {"index": {"NR": 0}}},
        "sex": {"category": {"index": {"T": 0}}},
        "age": {"category": {"index": {"TOTAL": 0}}},
        "icd10": {"category": {"index": {"C33_C34": 0}}},
        "resid": {"category": {"index": {"TOT_RESID": 0}}},
        "geo": {"category": {"index": {"EU27_2020": 0}, "label": {"EU27_2020": "EU27"}}},
        "time": {"category": {"index": {"2023": 0}}},
    },
    "value": {"0": 229920},
}


def _mock(asdr2: dict[str, Any] = _ASDR2, aro: dict[str, Any] | None = _ARO) -> None:
    respx.get(url__startswith=f"{API}/hlth_cd_asdr2").mock(
        return_value=httpx.Response(200, json=asdr2)
    )
    route = respx.get(url__startswith=f"{API}/hlth_cd_aro")
    route.mock(
        return_value=httpx.Response(200, json=aro) if aro is not None else httpx.Response(500)
    )


class TestFetchEpidemiology:
    @respx.mock
    async def test_shapes_the_country_bars_and_headline_figures(self) -> None:
        _mock()
        async with httpx.AsyncClient() as client:
            data = await fetch_epidemiology(client, "C33_C34")
        assert data is not None
        assert data["year"] == 2023
        assert "age-standardised" in data["unit"]
        # The EU aggregate and CH are read by their own codes, not from the bars.
        assert data["eu_asr"] == 46.65
        assert data["ch_asr"] == 34.77
        assert data["total_deaths"] == 229920

        bars = data["by_country"]
        codes = [b["geo"] for b in bars]
        # NUTS-2 sub-regions (BE21) never enter the per-country bars; the EU aggregate is not a
        # country either. Only two-letter country codes remain.
        assert "BE21" not in codes
        assert "EU27_2020" not in codes
        assert set(codes) == {"CH", "DE", "HU"}
        # Sorted by ASR, highest first: Hungary (80.07) > Germany (40) > Switzerland (34.77).
        assert codes == ["HU", "DE", "CH"]
        assert bars[0]["country"] == "Hungary"

    @respx.mock
    async def test_no_rate_reported_is_a_clean_empty_not_a_crash(self) -> None:
        empty = {**_ASDR2, "value": {}}
        _mock(asdr2=empty)
        async with httpx.AsyncClient() as client:
            data = await fetch_epidemiology(client, "C33_C34")
        # A site that exists in the dimension but carries no value -> None (the caller writes a
        # measured EMPTY), never a fabricated zero.
        assert data is None

    @respx.mock
    async def test_the_absolute_headline_is_best_effort(self) -> None:
        # The ASR view is the product; if the absolute-deaths dataset is down, the bars still
        # stand and total_deaths is simply absent -- never a guessed number.
        _mock(aro=None)
        async with httpx.AsyncClient() as client:
            data = await fetch_epidemiology(client, "C33_C34")
        assert data is not None
        assert data["total_deaths"] is None
        assert data["by_country"]  # unaffected
