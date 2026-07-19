#!/usr/bin/env python3
"""Gate 0 (Block A) -- verify Eurostat cancer mortality is fetchable with the fields Block A
needs AND that its icd10 dimension codes line up with the curated disease_source_map eurostat
source_codes. THROWAWAY, stdlib only.

Datasets probed:
  hlth_cd_asdr2  -- age-standardised death rate by residence (the ASR bars)
  hlth_cd_aro    -- causes of death, absolute number + crude rate (the absolute-deaths view?)

We must confirm: the ICD-10 site codes I mapped (C50, C33_C34, C91-C95, ...) EXIST in the
live icd10 dimension; the unit for ASR; that CH + EU are covered; the latest year available.
"""

from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
MAP_CSV = "D:/dev/xampp/htdocs/h2h-research-v2/backend/data/disease_source_map.csv"


def fetch(dataset: str, params: dict) -> dict:
    q = urllib.parse.urlencode({"format": "JSON", "lang": "EN", **params}, doseq=True)
    url = f"{API}/{dataset}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (h2h-research spike)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def describe(dataset: str, js: dict) -> None:
    print(f"\n=== {dataset} : {js.get('label')} ===")
    dims = js.get("id", [])
    sizes = js.get("size", [])
    print(f"dimensions (order): {list(zip(dims, sizes))}")
    for d in dims:
        cat = js["dimension"][d]["category"]
        idx = cat["index"]
        codes = list(idx) if isinstance(idx, list) else list(idx.keys())
        if len(codes) <= 25:
            print(f"  {d}: {codes}")
        else:
            print(f"  {d}: {len(codes)} codes, e.g. {codes[:8]} ...")


def icd10_codes(js: dict) -> set[str]:
    cat = js["dimension"]["icd10"]["category"]["index"]
    return set(cat if isinstance(cat, list) else cat.keys())


# my curated eurostat source_codes
def mapped_eurostat_codes() -> list[str]:
    out = []
    with open(MAP_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["source"] == "eurostat" and row["mondo_id"].strip():
                out.append(row["source_code"].strip())
    return out


# ---- ASR dataset ----
asr = fetch("hlth_cd_asdr2", {"sex": "T", "age": "TOTAL", "geo": "CH", "time": "2021"})
describe("hlth_cd_asdr2", asr)
live_icd = icd10_codes(asr)
print(f"\nlive icd10 dim: {len(live_icd)} codes")

mapped = mapped_eurostat_codes()
print(f"\n=== alignment: my {len(mapped)} mapped eurostat source_codes vs live icd10 ===")
missing = [c for c in mapped if c not in live_icd]
for c in mapped:
    print(f"  {c:12} {'OK' if c in live_icd else 'MISSING <<<'}")
print(f"\nMISSING ({len(missing)}): {missing}")

# a couple of sample ASR values for CH 2021
print("\n=== sample ASR values (CH, 2021, sex=T, age=TOTAL) ===")
dims = asr["id"]
icd_idx = asr["dimension"]["icd10"]["category"]["index"]
vals = asr["value"]
# size product for flat index -- icd10 is the only multi-valued dim here
for code in ["C50", "C33_C34", "C25", "C91-C95"]:
    pos = icd_idx.get(code)
    print(f"  {code}: pos={pos} value={vals.get(str(pos)) if pos is not None else 'n/a'}")
print("unit:", list(asr["dimension"]["unit"]["category"]["index"]))


# ---- absolute deaths dataset ----
try:
    aro = fetch("hlth_cd_aro", {"sex": "T", "age": "TOTAL", "geo": "CH", "time": "2021"})
    describe("hlth_cd_aro", aro)
    print("aro units:", list(aro["dimension"]["unit"]["category"]["index"]))
except Exception as e:  # noqa: BLE001
    print(f"\nhlth_cd_aro fetch failed: {e}")
