#!/usr/bin/env python3
"""H2H Phase 0 spike -- SEER (KEY: seer). THROWAWAY. stdlib only, no deps.

Measures COVERAGE = would a STAGE-WISE 5-year relative-survival block render
POPULATED per cancer, from the OPEN SEER*Explorer JSON endpoints (no login/key).

Endpoint (undocumented but public, what the web app itself calls):
  https://seer.cancer.gov/statistics-network/explorer/source/content_writers/render_region_5.php

Run:  python probe.py
"""
from __future__ import annotations
import json
import sys
import urllib.parse
import urllib.request

CW = "https://seer.cancer.gov/statistics-network/explorer/source/content_writers"
STAGE = {104: "Localized", 105: "Regional", 106: "Distant"}  # the block we need
STAGE_ALL = 101

# (label, site_code, sex_code, note). sex: 1=Both, 3=Female.
CANCERS = [
    ("NSCLC (proxy: Lung and Bronchus 47; incl. small cell)", 47, 1),
    ("Breast (Female)", 55, 3),
    ("Pancreatic carcinoma (Pancreas 40)", 40, 1),
    ("Melanoma of the Skin (53)", 53, 1),
    ("Chronic Myeloid Leukemia (97)", 97, 1),
]


def fetch(site: int, sex: int) -> dict:
    q = urllib.parse.urlencode({
        "site": site, "data_type": 4, "graph_type": 5, "compareBy": "stage",
        "relative_survival_interval": 5, "sex": sex, "race": 1,
        "age_range": 1, "data_model": 3, "series": "stage",
    })
    url = f"{CW}/render_region_5.php?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
    # endpoint double-encodes: a JSON string containing JSON
    obj = json.loads(body)
    if isinstance(obj, str):
        obj = json.loads(obj)
    return obj


def stage_map(payload: dict, site: int, sex: int) -> dict[int, float | None]:
    """stage_code -> rate, reading the sex_race_age_stage_subtype_site keys."""
    out: dict[int, float | None] = {}
    for key, row in payload.get("data", {}).items():
        parts = key.split("_")
        stg = int(parts[3])
        rate = row["data_series"][0][0]
        out[stg] = float(rate) if rate is not None else None
    return out


def main() -> int:
    print(f"{'cancer':52} {'Localized':>10} {'Regional':>10} {'Distant':>10}  state")
    print("-" * 100)
    populated = 0
    for label, site, sex in CANCERS:
        try:
            sm = stage_map(fetch(site, sex), site, sex)
        except Exception as e:  # noqa: BLE001 -- spike
            print(f"{label:52} {'SOURCE_FAILED -> ' + str(e)}")
            continue
        have = [s for s in STAGE if s in sm and sm[s] is not None]
        state = "POPULATED" if len(have) == len(STAGE) else "EMPTY (stage block)"
        if len(have) == len(STAGE):
            populated += 1

        def cell(s: int) -> str:
            return f"{sm[s]:.1f}%" if s in sm and sm[s] is not None else "--"
        allv = sm.get(STAGE_ALL)
        allstr = f"{allv:.1f}%" if allv is not None else "--"
        print(f"{label:52} {cell(104):>10} {cell(105):>10} {cell(106):>10}  "
              f"{state}   (All Stages: {allstr})")
    print("-" * 100)
    print(f"Stage-wise block POPULATED for {populated}/{len(CANCERS)} cancers.")
    print("CML returns only All-Stages -- leukemia is not decomposed into "
          "Localized/Regional/Distant (SS2000 solid-tumor schema does not apply).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
