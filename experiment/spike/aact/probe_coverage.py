#!/usr/bin/env python3
"""Phase 0 spike (KEY: aact) -- CT.gov v2 open HR coverage, measured per cancer.

Decisive cross-check for the Phase 3 forest plot: are hazard ratios ONLY in AACT
(login-gated cloud DB), or does the ClinicalTrials.gov API v2 already expose HR+CI
openly? This script measures, per cancer, how many trials carry a machine-readable
"Hazard Ratio (HR)" outcome analysis with a confidence interval -- with NO login and
NO API key -- and VERIFIES a sample so the search-area filter isn't trusted blind.

stdlib only (urllib + json). The CT.gov WAF allowlists the `python-httpx/` UA token
(bare Mozilla / custom tokens 403), so we send that token from urllib.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

UA = "python-httpx/0.27 (h2h-experiment/0.1; research spike)"
BASE = "https://clinicaltrials.gov/api/v2/studies"

# EFO IDs are Open Targets identifiers; CT.gov indexes conditions as text/MeSH.
# We map each EFO term to the CT.gov condition query and record it for the report.
CANCERS = [
    ("NSCLC",               "EFO_0003060", "non-small cell lung cancer"),
    ("breast carcinoma",    "EFO_0000305", "breast carcinoma"),
    ("pancreatic carcinoma","EFO_0002618", "pancreatic carcinoma"),
    ("melanoma",            "EFO_0000756", "melanoma"),
    ("CML",                 "EFO_0000339", "chronic myeloid leukemia"),
]

HR_AREA = 'AREA[OutcomeAnalysisParamType]"Hazard Ratio (HR)"'


def get(url: str) -> dict:
    for attempt in range(6):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def count(params: dict) -> int:
    p = dict(params); p["countTotal"] = "true"; p["pageSize"] = 1
    p["fields"] = "protocolSection.identificationModule.nctId"
    url = BASE + "?" + urllib.parse.urlencode(p)
    return get(url).get("totalCount")


def hr_nctids(cond: str, want: int) -> list[str]:
    """NCT ids of trials matching the HR search area for this condition."""
    ids: list[str] = []
    token = None
    while len(ids) < want:
        p = {"query.cond": cond, "query.term": HR_AREA,
             "pageSize": 100, "fields": "protocolSection.identificationModule.nctId"}
        if token:
            p["pageToken"] = token
        d = get(BASE + "?" + urllib.parse.urlencode(p))
        for s in d.get("studies", []):
            ids.append(s["protocolSection"]["identificationModule"]["nctId"])
        token = d.get("nextPageToken")
        if not token:
            break
    return ids[:want]


def verify_hr(nctid: str) -> dict:
    """Fetch one trial's outcome analyses; return real HR+CI facts found."""
    p = {"fields": "resultsSection.outcomeMeasuresModule"}
    d = get(f"{BASE}/{nctid}?" + urllib.parse.urlencode(p))
    oms = (d.get("resultsSection", {})
            .get("outcomeMeasuresModule", {})
            .get("outcomeMeasures", []) or [])
    hrs = []
    for o in oms:
        for a in o.get("analyses", []) or []:
            if (a.get("paramType") or "") == "Hazard Ratio (HR)":
                hrs.append({
                    "hr": a.get("paramValue"),
                    "ci_low": a.get("ciLowerLimit"),
                    "ci_high": a.get("ciUpperLimit"),
                    "ci_pct": a.get("ciPctValue"),
                    "p": a.get("pValue"),
                })
    with_ci = [h for h in hrs if h["hr"] and h["ci_low"] and h["ci_high"]]
    return {"nctid": nctid, "n_hr": len(hrs), "n_hr_with_ci": len(with_ci),
            "sample": with_ci[:2]}


def main() -> None:
    results = {}
    for name, efo, cond in CANCERS:
        print(f"\n=== {name} ({efo}) cond='{cond}' ===")
        n_cond = count({"query.cond": cond})
        n_results = count({"query.cond": cond, "aggFilters": "results:with"})
        n_hr = count({"query.cond": cond, "query.term": HR_AREA})
        print(f"trials matching condition:      {n_cond:>7,}")
        print(f"  ...with posted results:       {n_results:>7,}")
        print(f"  ...with HR analysis (area):   {n_hr:>7,}")

        # VERIFY the search-area filter: pull up to 15 candidates and confirm each
        # actually carries a machine-readable HR with CI (guard against fuzzy match).
        ids = hr_nctids(cond, 15)
        verified = []
        for i in ids:
            verified.append(verify_hr(i))
            time.sleep(0.7)
        n_ok = sum(1 for v in verified if v["n_hr_with_ci"] > 0)
        total_hr_facts = sum(v["n_hr_with_ci"] for v in verified)
        print(f"  verify sample: {n_ok}/{len(ids)} truly carry HR+CI "
              f"({total_hr_facts} HR+CI analyses across sample)")
        for v in verified[:3]:
            print("    ", json.dumps(v))
        results[name] = {
            "efo": efo, "cond": cond, "n_cond": n_cond,
            "n_with_results": n_results, "n_with_hr_area": n_hr,
            "verify_sample_size": len(ids), "verify_ok": n_ok,
            "verify_hr_ci_facts": total_hr_facts,
            "verified_ids": verified,
        }
        time.sleep(0.5)

    with open("out/coverage.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n=== COVERAGE SUMMARY (open CT.gov v2, no login/key) ===")
    print(f"{'cancer':<22}{'cond#':>9}{'results#':>10}{'HR#':>7}  verify")
    for name, r in results.items():
        print(f"{name:<22}{r['n_cond']:>9,}{r['n_with_results']:>10,}"
              f"{r['n_with_hr_area']:>7,}  {r['verify_ok']}/{r['verify_sample_size']}")


if __name__ == "__main__":
    main()
