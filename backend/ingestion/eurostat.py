"""Eurostat cancer-mortality adapter.

Age-standardised death rate (ASR) by country from `hlth_cd_asdr2`, plus the EU total deaths
from `hlth_cd_aro` -- open Eurostat data, redistributable (no non-commercial clause). The ASR
is the honest cross-country-comparable figure; absolute deaths mostly track population size, so
they are a single EU headline here, never a per-country chart.

This is a thin mapping of the JSON-stat payload. It is handed an ICD-10 site code (the resolved
Eurostat category from the disease map, e.g. `C33_C34`), NOT a disease name -- the vocabulary
crossing already happened in the mapping layer.
"""

from __future__ import annotations

from typing import Any

import httpx

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

# Eurostat's REST endpoint is lenient, but our shared client's python-httpx UA is not what the
# spike verified; send the browser UA the probes used, per request, to stay on the tested path.
_HEADERS = {"User-Agent": "Mozilla/5.0 (h2h-research; eurostat adapter)"}

# The EU aggregate (post-Brexit composition) -- the reference ASR + the total-deaths headline.
EU = "EU27_2020"

_ASR_UNIT = "per 100 000 inhabitants, age-standardised"


async def _get(client: httpx.AsyncClient, dataset: str, params: dict[str, Any]) -> dict[str, Any]:
    r = await client.get(
        f"{API}/{dataset}",
        params={"format": "JSON", "lang": "EN", **params},
        headers=_HEADERS,
    )
    r.raise_for_status()
    js: dict[str, Any] = r.json()
    return js


def _series(js: dict[str, Any], varying: str) -> dict[str, tuple[float, str]]:
    """Read a JSON-stat cube where only `varying` has many categories (every other dimension
    was pinned to one value in the query). Returns {code: (value, label)} for present cells.

    JSON-stat stores values in a sparse flat map keyed by the row-major index; with all other
    dimensions at position 0, a category's flat index is just its position times its stride.
    """
    dims: list[str] = js["id"]
    size: list[int] = js["size"]
    values: dict[str, float] = js["value"]
    strides = [1] * len(dims)
    for i in range(len(dims) - 2, -1, -1):
        strides[i] = strides[i + 1] * size[i + 1]
    stride = strides[dims.index(varying)]

    cat = js["dimension"][varying]["category"]
    index = cat["index"]
    # JSON-stat encodes a dimension's categories either as {code: position} or as an ordered
    # list where the position IS the list index. Normalise both to (code, position) pairs.
    pairs: list[tuple[str, int]] = (
        list(index.items()) if isinstance(index, dict) else [(c, i) for i, c in enumerate(index)]
    )
    labels: dict[str, str] = cat.get("label") or {}
    out: dict[str, tuple[float, str]] = {}
    for code, pos in pairs:
        v = values.get(str(pos * stride))
        if v is not None:
            out[code] = (float(v), labels.get(code, code))
    return out


def _latest_year(js: dict[str, Any]) -> str:
    times = js["dimension"]["time"]["category"]["index"]
    codes: list[str] = list(times)
    return max(codes, key=int)


async def fetch_epidemiology(client: httpx.AsyncClient, icd10: str) -> dict[str, Any] | None:
    """European mortality for one ICD-10 cancer site.

    Returns the epidemiology payload, or None when Eurostat resolved the site but has no data
    for it (a real EMPTY). Raises on transport/parse failure -- the caller records that as a
    source_failed fact, never as "no deaths".
    """
    # ASR by geography, latest year. lastTimePeriod=1 pins time to a single (most recent)
    # period, so each country's cell is a plain position lookup and every bar is the same year.
    asr_js = await _get(
        client,
        "hlth_cd_asdr2",
        {"sex": "T", "age": "TOTAL", "icd10": icd10, "lastTimePeriod": 1},
    )
    year = _latest_year(asr_js)
    asr = _series(asr_js, "geo")
    if not asr:
        return None  # site exists in the dimension but no rate reported -> EMPTY

    # Country level only: the dataset is "by NUTS 2 region", so it also carries sub-national
    # units (BE21, ...). Country codes are the two-letter NUTS-0 codes; EU27_2020 is the
    # aggregate we treat separately. Sub-national regions never enter the per-country bars.
    rows: list[dict[str, Any]] = [
        {"geo": code, "country": label, "asr": round(v, 2)}
        for code, (v, label) in asr.items()
        if len(code) == 2
    ]
    by_country = sorted(rows, key=lambda r: r["asr"], reverse=True)
    eu_asr = round(asr[EU][0], 2) if EU in asr else None
    ch_asr = round(asr["CH"][0], 2) if "CH" in asr else None

    # The EU total deaths headline (absolute), residents basis. A best-effort figure: if aro is
    # unavailable or lacks the EU aggregate for this year, the ASR view still stands without it.
    total_deaths: int | None = None
    try:
        aro_js = await _get(
            client,
            "hlth_cd_aro",
            {
                "sex": "T",
                "age": "TOTAL",
                "icd10": icd10,
                "resid": "TOT_RESID",
                "geo": EU,
                "time": year,
            },
        )
        eu_deaths = _series(aro_js, "geo").get(EU)
        if eu_deaths is not None:
            total_deaths = int(eu_deaths[0])
    except (httpx.HTTPError, KeyError, ValueError):
        total_deaths = None

    return {
        "year": int(year),
        "unit": _ASR_UNIT,
        "eu_asr": eu_asr,
        "ch_asr": ch_asr,
        "total_deaths": total_deaths,
        "by_country": by_country,
    }
