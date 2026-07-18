"""Phase 0 spike: ClinicalTrials.gov API v2 coverage probe (KEY: ctgov).

Throwaway. stdlib only (urllib + json), no deps. Makes REAL calls and measures
whether the "trial-reality" evidence block would render POPULATED per cancer.

Measures, per cancer:
 (a) totalCount by condition (query.cond)
 (b) whyStopped populated fraction among TERMINATED+WITHDRAWN
 (c) RECRUITING trials filterable by country (Switzerland/Germany/Austria)
 (d) hazard-ratio fraction among COMPLETED-with-results (Phase 3 gate)

Run: uv run python probe.py   (or plain python; stdlib only)
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

BASE = "https://clinicaltrials.gov/api/v2/studies"

# v2 does NOT require the v1 WAF User-Agent workaround: curl's default UA and a
# bare urllib UA both return 200. We still send a descriptive UA as a courtesy /
# to stay robust if the WAF tightens.
UA = "python-urllib (h2h-spike/0.1 ctgov; research spike)"

# ctgov keys on condition TEXT, not EFO. The EFO IDs in the task are Open Targets
# identifiers; here we verify each condition string resolves to the right disease
# by eyeballing returned briefTitles (done manually in report). Mapping:
CANCERS = {
    "NSCLC": "non-small cell lung carcinoma",
    "breast": "breast carcinoma",
    "pancreatic": "pancreatic carcinoma",
    "melanoma": "melanoma",
    "CML": "chronic myeloid leukemia",
}


def get(params: dict) -> dict:
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def total(params: dict) -> int:
    p = dict(params, countTotal="true", pageSize=0)
    return get(p).get("totalCount")


def paginate(params: dict, cap: int = 5000):
    """Yield studies across pages up to cap."""
    p = dict(params, pageSize=1000)
    n = 0
    while True:
        body = get(p)
        studies = body.get("studies", [])
        for s in studies:
            yield s
            n += 1
        tok = body.get("nextPageToken")
        if not tok or n >= cap:
            break
        p["pageToken"] = tok


# ---------------------------------------------------------------------------
# (a) trial counts by condition
# ---------------------------------------------------------------------------
print("=" * 70)
print("(a) totalCount by condition")
print("=" * 70)
counts = {}
for key, cond in CANCERS.items():
    tc = total({"query.cond": cond})
    counts[key] = tc
    print(f"  {key:12s} ({cond}): {tc}")

# ---------------------------------------------------------------------------
# (b) whyStopped populated fraction among TERMINATED + WITHDRAWN
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("(b) whyStopped fraction among TERMINATED + WITHDRAWN")
print("=" * 70)
why = {}
for key, cond in CANCERS.items():
    params = {
        "query.cond": cond,
        "filter.overallStatus": "TERMINATED|WITHDRAWN",
        "fields": ",".join(
            [
                "protocolSection.identificationModule.nctId",
                "protocolSection.statusModule.overallStatus",
                "protocolSection.statusModule.whyStopped",
            ]
        ),
    }
    tc = total(params)
    n_scanned = 0
    n_why = 0
    for s in paginate(params):
        n_scanned += 1
        sm = s.get("protocolSection", {}).get("statusModule", {})
        w = sm.get("whyStopped")
        if w and w.strip():
            n_why += 1
    frac = (n_why / n_scanned * 100) if n_scanned else 0
    why[key] = (tc, n_scanned, n_why, frac)
    print(
        f"  {key:12s}: {tc} terminated/withdrawn total, "
        f"{n_scanned} scanned, {n_why} with whyStopped ({frac:.1f}%)"
    )

# ---------------------------------------------------------------------------
# (c) RECRUITING trials filterable by country
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("(c) RECRUITING trials by country (geo/location filter)")
print("=" * 70)
loc = {}
for key, cond in CANCERS.items():
    row = {}
    for country in ("Switzerland", "Germany", "Austria"):
        params = {
            "query.cond": cond,
            "filter.overallStatus": "RECRUITING",
            "query.locn": country,
        }
        tc = total(params)
        row[country] = tc
    loc[key] = row
    print(
        f"  {key:12s}: RECRUITING  CH={row['Switzerland']}  "
        f"DE={row['Germany']}  AT={row['Austria']}"
    )

# Prove real Swiss trials come back (NCT ids + a location) for NSCLC and breast
print()
print("  -- sample RECRUITING Swiss trials (NSCLC, breast) --")
for key in ("NSCLC", "breast"):
    params = {
        "query.cond": CANCERS[key],
        "filter.overallStatus": "RECRUITING",
        "query.locn": "Switzerland",
        "pageSize": 3,
        "fields": ",".join(
            [
                "protocolSection.identificationModule.nctId",
                "protocolSection.identificationModule.briefTitle",
                "protocolSection.contactsLocationsModule.locations",
            ]
        ),
    }
    body = get(params)
    for s in body.get("studies", []):
        idm = s["protocolSection"]["identificationModule"]
        locs = s.get("protocolSection", {}).get("contactsLocationsModule", {}).get(
            "locations", []
        )
        ch = [l for l in locs if l.get("country") == "Switzerland"]
        cities = ", ".join(sorted({l.get("city", "?") for l in ch}))
        print(f"    {key}: {idm['nctId']}  CH cities: {cities}")

# ---------------------------------------------------------------------------
# (d) HAZARD RATIOS among COMPLETED-with-results (Phase 3 gate)
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("(d) Hazard ratio fraction among COMPLETED trials WITH results")
print("=" * 70)
hr = {}
for key, cond in CANCERS.items():
    # Trials that have posted results (aggregate analysis available)
    params = {
        "query.cond": cond,
        "filter.overallStatus": "COMPLETED",
        "aggFilters": "results:with",
        "fields": ",".join(
            [
                "protocolSection.identificationModule.nctId",
                "resultsSection.outcomeMeasuresModule.outcomeMeasures.analyses",
            ]
        ),
    }
    tc_results = total(params)
    n_scanned = 0
    n_hr = 0
    hr_examples = []
    # Cap scan to keep runtime sane; report the cap explicitly.
    for s in paginate(params, cap=600):
        n_scanned += 1
        oms = (
            s.get("resultsSection", {})
            .get("outcomeMeasuresModule", {})
            .get("outcomeMeasures", [])
        )
        found_hr = False
        for om in oms:
            for an in om.get("analyses", []) or []:
                pt = (an.get("paramType") or "").upper()
                if "HAZARD" in pt or pt == "HR":
                    found_hr = True
                    if len(hr_examples) < 3:
                        ci_l = an.get("ciLowerLimit")
                        ci_u = an.get("ciUpperLimit")
                        hr_examples.append(
                            (
                                s["protocolSection"]["identificationModule"]["nctId"],
                                an.get("paramValue"),
                                ci_l,
                                ci_u,
                            )
                        )
        if found_hr:
            n_hr += 1
    frac = (n_hr / n_scanned * 100) if n_scanned else 0
    hr[key] = (tc_results, n_scanned, n_hr, frac, hr_examples)
    print(
        f"  {key:12s}: {tc_results} completed-with-results, "
        f"{n_scanned} scanned, {n_hr} carry >=1 HAZARD_RATIO analysis ({frac:.1f}%)"
    )
    for ex in hr_examples:
        print(f"      e.g. {ex[0]}: HR={ex[1]} CI[{ex[2]}, {ex[3]}]")

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
for key in CANCERS:
    tc = counts[key]
    _, wscan, wn, wf = why[key]
    ch = loc[key]["Switzerland"]
    trc, hscan, hn, hf, _ = hr[key]
    pop = "POPULATED" if (tc and wscan and ch is not None) else "check"
    print(
        f"  {key:12s}: trials={tc}  whyStopped={wn}/{wscan} ({wf:.0f}%)  "
        f"CH_recruiting={ch}  HR={hn}/{hscan} ({hf:.1f}%)  [{pop}]"
    )
