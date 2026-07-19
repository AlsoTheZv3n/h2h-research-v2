#!/usr/bin/env python3
"""Gate 0 (Block B) -- confirm the SEER render_region_5 payload carries rate + SE + 95% CI +
case count per stage (the 5-tuple Block B needs), across the SEER site codes the mapping uses
beyond the original 5 -- especially the post-Gate-1 nodes (76 CNS, 661 GBM, 90 leukemia,
96 AML). THROWAWAY, stdlib only."""

from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request

CW = "https://seer.cancer.gov/statistics-network/explorer/source/content_writers"
STAGE = {104: "Localized", 105: "Regional", 106: "Distant", 101: "All Stages"}
MAP_CSV = "D:/dev/xampp/htdocs/h2h-research-v2/backend/data/disease_source_map.csv"


def fetch(site: int, sex: int = 1) -> dict:
    q = urllib.parse.urlencode({
        "site": site, "data_type": 4, "graph_type": 5, "compareBy": "stage",
        "relative_survival_interval": 5, "sex": sex, "race": 1,
        "age_range": 1, "data_model": 3, "series": "stage",
    })
    req = urllib.request.Request(f"{CW}/render_region_5.php?{q}",
                                 headers={"User-Agent": "Mozilla/5.0 (h2h spike)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        obj = json.loads(r.read().decode("utf-8"))
    return json.loads(obj) if isinstance(obj, str) else obj


def mapped_seer() -> list[tuple[str, str]]:
    out = []
    with open(MAP_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["source"] == "seer" and row["mondo_id"].strip():
                out.append((row["source_code"].strip(), row["source_label"].strip()))
    return out


# dump the raw 5-tuple for one solid tumor to confirm structure
print("=== raw data_series shape (site 55 Breast, sex=3) ===")
p = fetch(55, sex=3)
for key, row in list(p.get("data", {}).items())[:6]:
    stg = int(key.split("_")[3])
    print(f"  stage {stg:3} {STAGE.get(stg, '?'):11} data_series[0]={row['data_series'][0]}")
print("  (expected [rate, SE, ci_lo, ci_hi, count])")

print("\n=== per mapped SEER site: does the stage block populate? (rate | count) ===")
for code, label in mapped_seer():
    try:
        site = int(code)
    except ValueError:
        print(f"  {code:5} {label[:32]:32} non-numeric site code"); continue
    sex = 3 if site == 55 else 1  # breast -> female cohort
    try:
        sm = {}
        for key, row in fetch(site, sex).get("data", {}).items():
            stg = int(key.split("_")[3])
            ds = row["data_series"][0]
            sm[stg] = (ds[0], ds[4] if len(ds) > 4 else None)  # rate, count
    except Exception as e:  # noqa: BLE001
        print(f"  {code:5} {label[:32]:32} SOURCE_FAILED {e}"); continue
    staged = all(s in sm and sm[s][0] is not None for s in (104, 105, 106))
    allv = sm.get(101, (None, None))
    print(f"  {code:5} {label[:32]:32} staged={'Y' if staged else 'N':1} "
          f"AllStages={allv[0]}  n={allv[1]}")
