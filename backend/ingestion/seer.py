"""SEER survival adapter.

Stage-wise 5-year RELATIVE survival from SEER*Explorer's public aggregate endpoint -- open,
no login, no data-use agreement (that gates only the case-level microdata, which we never
touch). U.S. federal work, effectively public domain with attribution.

Handed a SEER numeric SITE code (the resolved category from the disease map, e.g. 47 Lung),
NOT a disease name. Returns the stages, each a 5-year relative-survival rate with its 95% CI,
case count and share of cases. Leukemias are not decomposed into Localized/Regional/Distant
(the SS2000 solid-tumor stage schema does not apply), so their stage block is a real, measured
EMPTY -- `staged` is False and only the All-Stages figure is returned, never a zero.

The endpoint is undocumented and internal; its structure is pinned by the adapter tests so a
schema drift fails loudly rather than silently mis-parsing.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

CONTENT_WRITERS = "https://seer.cancer.gov/statistics-network/explorer/source/content_writers"
_HEADERS = {"User-Agent": "Mozilla/5.0 (h2h-research; seer adapter)"}

# SS2000 summary-stage codes (NOT TNM). 101 is the All-Stages roll-up; 104/105/106 are the
# stage block; 107 (Unstaged) is deliberately not shown -- it is not a prognostic stage.
_ALL_STAGES = 101
_STAGES = {104: "Localized", 105: "Regional", 106: "Distant"}

# Breast defaults to the female cohort; passing sex=1 (Both) returns the male subset for the
# female-dominant site. Every other mapped site reads correctly as Both.
_SEX = {55: 3}

METRIC = "5-year relative survival"


async def _fetch_raw(client: httpx.AsyncClient, site: int) -> dict[str, Any]:
    params: dict[str, str | int] = {
        "site": site,
        "data_type": 4,  # Survival
        "graph_type": 5,  # 5-Year Survival
        "compareBy": "stage",
        "relative_survival_interval": 5,
        "sex": _SEX.get(site, 1),
        "race": 1,  # All races
        "age_range": 1,  # All ages
        "data_model": 3,  # Preliminary Estimates (Selected Registries 2000-2024)
        "series": "stage",
    }
    r = await client.get(f"{CONTENT_WRITERS}/render_region_5.php", params=params, headers=_HEADERS)
    r.raise_for_status()
    # The endpoint double-encodes: a JSON string whose content is JSON. Parse twice.
    raw: Any = r.json()
    if isinstance(raw, str):
        raw = json.loads(raw)
    payload: dict[str, Any] = raw
    return payload


def _num(x: Any) -> float | None:
    """SEER sends numbers as strings, and null for a suppressed/capped bound."""
    if x is None or x == "":
        return None
    try:
        parsed: float = float(x)
    except (TypeError, ValueError):
        return None
    return parsed


def _parse(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """stage_code -> {rate, ci_low, ci_high, se, n}, from the sex_race_age_stage_subtype_site
    row keys. data_series[0] = [rate, standard_error, ci_lower, ci_upper, count]."""
    out: dict[int, dict[str, Any]] = {}
    for key, row in payload.get("data", {}).items():
        parts = key.split("_")
        if len(parts) < 4:
            continue
        stage = int(parts[3])
        ds = (row.get("data_series") or [[]])[0]
        if not ds:
            continue
        out[stage] = {
            "rate": _num(ds[0]),
            "se": _num(ds[1]) if len(ds) > 1 else None,
            "ci_low": _num(ds[2]) if len(ds) > 2 else None,
            "ci_high": _num(ds[3]) if len(ds) > 3 else None,
            "n": int(ds[4]) if len(ds) > 4 and ds[4] is not None else None,
        }
    return out


async def fetch_survival(client: httpx.AsyncClient, site: int) -> dict[str, Any] | None:
    """5-year relative survival for one SEER site.

    Returns the survival payload, or None when the site returns nothing at all (a real EMPTY).
    Raises on transport/parse failure -- recorded by the caller as source_failed, never as 0%.
    """
    stages = _parse(await _fetch_raw(client, site))
    overall = stages.get(_ALL_STAGES)
    if overall is None or overall["rate"] is None:
        return None  # nothing to report for this site -> EMPTY

    total_n: int | None = overall.get("n")

    def _share(n: int | None) -> float | None:
        if n is None or not total_n:
            return None
        return round(n / total_n, 4)

    by_stage = [
        {
            "stage": label,
            "rate": stages[code]["rate"],
            "ci_low": stages[code]["ci_low"],
            "ci_high": stages[code]["ci_high"],
            "n": stages[code]["n"],
            "share": _share(stages[code]["n"]),
        }
        for code, label in _STAGES.items()
        if code in stages and stages[code]["rate"] is not None
    ]
    # Staged only when the full solid-tumor block is present; leukemias yield All-Stages alone.
    staged = len(by_stage) == len(_STAGES)

    return {
        "metric": METRIC,
        "staged": staged,
        "all_stages": {
            "rate": overall["rate"],
            "ci_low": overall["ci_low"],
            "ci_high": overall["ci_high"],
            "n": total_n,
        },
        "by_stage": by_stage if staged else [],
    }
