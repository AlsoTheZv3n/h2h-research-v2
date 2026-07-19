#!/usr/bin/env python3
"""S3 -- Observed combinations: combination or comparison? THROWAWAY.

A trial naming drug A and drug B may be A+B (combination) or A vs B (comparison) -- opposite
meanings. Only the ARM structure distinguishes them. For ~20 oncology drugs, pull trials and
measure: of the MULTI-drug trials, what share can be classified UNAMBIGUOUSLY from the
structured arm fields (a single arm holding >=2 drugs = combination; >=2 arms each holding a
different single drug = comparison). Everything else is ambiguous.

Run:  uv run python s3_combinations.py
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

CT = "https://clinicaltrials.gov/api/v2/studies"
UA = "python-httpx/0.27 (h2h-spike-backlog; research)"

DRUGS = [
    "pembrolizumab", "nivolumab", "trastuzumab", "bevacizumab", "osimertinib", "cetuximab",
    "rituximab", "carboplatin", "paclitaxel", "olaparib", "ipilimumab", "atezolizumab",
    "durvalumab", "ramucirumab", "gemcitabine", "docetaxel", "sunitinib", "sorafenib",
    "lenvatinib", "cabozantinib",
]
DRUG_TYPES = {"DRUG", "BIOLOGICAL"}


def _get(url: str) -> dict:
    for attempt in range(6):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def trials(drug: str, want: int) -> list[dict]:
    out: list[dict] = []
    token = None
    while len(out) < want:
        p = {
            "query.intr": drug, "pageSize": 200,
            "fields": "protocolSection.armsInterventionsModule",
        }
        if token:
            p["pageToken"] = token
        d = _get(CT + "?" + urllib.parse.urlencode(p))
        out.extend(d.get("studies", []))
        token = d.get("nextPageToken")
        if not token:
            break
        time.sleep(0.4)
    return out[:want]


def is_drug_name(name: str) -> bool:
    n = name.lower()
    return not any(w in n for w in ("placebo", "saline", "best supportive", "observation"))


def classify(mod: dict) -> str:
    """single-drug | combination | comparison | ambiguous(multi-drug, unparseable)."""
    interventions = mod.get("interventions") or []
    drugs = {i["name"] for i in interventions if i.get("type") in DRUG_TYPES and is_drug_name(i.get("name", ""))}
    if len(drugs) < 2:
        return "single-drug"
    arms = mod.get("armGroups") or []
    arm_drugsets = [
        {n for n in (a.get("interventionNames") or []) if is_drug_name(n)}
        for a in arms
    ]
    arm_drugsets = [s for s in arm_drugsets if s]  # arms that actually name a drug
    if not arm_drugsets:
        return "ambiguous"  # multi-drug but no arm-level assignment -> cannot tell combo vs comparison
    combo = any(len(s) >= 2 for s in arm_drugsets)
    single_drug_arms = [next(iter(s)) for s in arm_drugsets if len(s) == 1]
    comparison = len(set(single_drug_arms)) >= 2
    if combo or comparison:
        return "combination" if combo else "comparison"
    return "ambiguous"


def main() -> None:
    total = Counter()
    for drug in DRUGS:
        try:
            ts = trials(drug, 150)
        except Exception as e:  # noqa: BLE001
            print(f"  {drug}: ERROR {e}")
            continue
        c = Counter(classify(t.get("protocolSection", {}).get("armsInterventionsModule", {})) for t in ts)
        total.update(c)
    multi = total["combination"] + total["comparison"] + total["ambiguous"]
    classifiable = total["combination"] + total["comparison"]
    print("=== across ~20 oncology drugs ===")
    for k in ("single-drug", "combination", "comparison", "ambiguous"):
        print(f"  {k:12} {total[k]}")
    print(f"\n  multi-drug trials: {multi}")
    print(f"  unambiguously classifiable (combo|comparison): {classifiable} "
          f"({100*classifiable/multi:.1f}% of multi-drug)")
    print(f"  ambiguous (multi-drug, unparseable arm structure): {total['ambiguous']} "
          f"({100*total['ambiguous']/multi:.1f}%)")


if __name__ == "__main__":
    main()
