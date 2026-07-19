"""The SEER survival adapter. The endpoint is undocumented and internal, so these tests pin
its two traps -- the double JSON encoding and the sex_race_age_STAGE_subtype_site row keys --
and the honest shaping: solid tumours are staged, leukemias carry only the All-Stages figure
(a real EMPTY for the stage block, never a zero), the Unstaged row is dropped, capped bounds
stay null."""

from __future__ import annotations

import json
from typing import Any

import httpx
import respx

from backend.ingestion.seer import CONTENT_WRITERS, fetch_survival


def _row(rate: str, se: str, lo: str | None, hi: str | None, n: int) -> dict[str, Any]:
    return {"data_series": [[rate, se, lo, hi, n]]}


# Row keys are sex_race_age_STAGE_subtype_site; stage codes 101 All / 104 Loc / 105 Reg /
# 106 Dist / 107 Unstaged. Localized here carries null CI bounds (a capped 100% rate), which
# must survive as None, not 0.
_SOLID = {
    "data": {
        "1_1_1_101_0_47": _row("29.5", "0.1", "29.2", "29.7", 390184),
        "1_1_1_104_0_47": _row("100.0", "0.004", None, None, 92662),
        "1_1_1_105_0_47": _row("38.2", "0.2", "37.8", "38.6", 80220),
        "1_1_1_106_0_47": _row("10.5", "0.1", "10.3", "10.7", 200434),
        "1_1_1_107_0_47": _row("20.0", "0.5", "19.0", "21.0", 16868),  # Unstaged -> ignored
    }
}

# Leukemia: only All-Stages -- the SS2000 solid-tumor stages do not apply.
_LEUKEMIA = {"data": {"1_1_1_101_0_90": _row("68.6", "0.2", "68.2", "69.0", 118580)}}


def _mock(payload: dict[str, Any]) -> None:
    # The endpoint double-encodes (a JSON string whose content is JSON); json=json.dumps(...)
    # reproduces exactly that so the adapter's double-decode is exercised, not bypassed.
    respx.get(url__startswith=f"{CONTENT_WRITERS}/render_region_5.php").mock(
        return_value=httpx.Response(200, json=json.dumps(payload))
    )


class TestFetchSurvival:
    @respx.mock
    async def test_parses_a_double_encoded_staged_solid_tumour(self) -> None:
        _mock(_SOLID)
        async with httpx.AsyncClient() as client:
            data = await fetch_survival(client, 47)
        assert data is not None
        assert data["staged"] is True
        assert data["metric"] == "5-year relative survival"

        alls = data["all_stages"]
        assert alls["rate"] == 29.5
        assert alls["n"] == 390184
        assert (alls["ci_low"], alls["ci_high"]) == (29.2, 29.7)

        stages = {s["stage"]: s for s in data["by_stage"]}
        # The Unstaged row (107) is not a prognostic stage and is dropped.
        assert set(stages) == {"Localized", "Regional", "Distant"}
        # A capped bound stays None, never a fabricated 0.
        assert stages["Localized"]["rate"] == 100.0
        assert stages["Localized"]["ci_low"] is None
        # share = this stage's cases / all-stages cases.
        assert stages["Localized"]["share"] == round(92662 / 390184, 4)
        assert stages["Distant"]["rate"] == 10.5

    @respx.mock
    async def test_leukemia_is_not_staged_but_keeps_the_all_stages_figure(self) -> None:
        _mock(_LEUKEMIA)
        async with httpx.AsyncClient() as client:
            data = await fetch_survival(client, 90)
        assert data is not None
        # Not stage-decomposed: a real EMPTY for the stage block, never a zero -- and the plain
        # All-Stages survival still stands.
        assert data["staged"] is False
        assert data["by_stage"] == []
        assert data["all_stages"]["rate"] == 68.6
        assert data["all_stages"]["n"] == 118580

    @respx.mock
    async def test_nothing_at_all_is_a_clean_empty(self) -> None:
        _mock({"data": {}})
        async with httpx.AsyncClient() as client:
            data = await fetch_survival(client, 999)
        assert data is None
