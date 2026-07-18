#!/usr/bin/env python3
"""GLOBOCAN / IARC Global Cancer Observatory -- Phase 0 data spike (KEY: globocan).

Throwaway probe. Uses ONLY the Python stdlib (urllib + json) -- no deps, no uv add.
Answers: can we retrieve age-standardised rates (ASR) for incidence + mortality,
per cancer x country, OPENLY (no login/key) and MACHINE-READABLY, for the 5 target
cancers?

The public site (https://gco.iarc.who.int/today) is a Vue SPA. The real programmatic
path was found by reading its bundle (today/assets/main-*.js): a JSON REST gateway
  VITE_APP_API = https://gco.iarc.who.int/gateway_prod/api/globocan/v3/[vdb]/
with [vdb] = data_version = "2024" (this is the GLOBOCAN 2022 estimates release).

Endpoints used:
  /meta/cancers/all/                 -> cancer site codes (ICD-10 based)
  /meta/populations/all/             -> country/region codes (ISO numeric)
  /data/rate/{sex}/{type}/{pop}/all/ -> per-cancer rows incl. `asr`
    sex axis : 0=both 1=male 2=female     (returned in rows as `sex`)
    type axis: 0=incidence 1=mortality 2=prevalence (returned as `type`)
    the two path segments 0_1_2/0_1_2 just request all sexes+types at once.

Run:  python probe.py
"""
from __future__ import annotations
import json
import urllib.request

BASE = "https://gco.iarc.who.int/gateway_prod/api/globocan/v3/2024"
QS = "?group_CRC=1&include_nmsc=1&include_nmsc_other=1"

# GLOBOCAN cancer-site codes (verified against /meta/cancers/all/ -- see report).
# The 5 targets are given as Open Targets EFO ids; GLOBOCAN has NO EFO/histology axis,
# it is ICD-10 site-based, so each maps to a SITE (exact) or only an AGGREGATE (proxy).
TARGETS = {
    "NSCLC (EFO_0003060)":            (15, "Trachea, bronchus and lung C33-34", "PROXY: site-level lung only; NSCLC histology not separable"),
    "breast carcinoma (EFO_0000305)": (20, "Breast C50",                        "EXACT"),
    "pancreatic ca (EFO_0002618)":    (13, "Pancreas C25",                       "EXACT"),
    "melanoma (EFO_0000756)":         (16, "Melanoma of skin C43",               "EXACT"),
    "CML (EFO_0000339)":              (36, "Leukaemia C91-95",                   "NONE: all-leukaemia aggregate only; CML not separable"),
}
COUNTRIES = {"World": 900, "United States": 840, "United Kingdom": 826, "Japan": 392}


def get(path: str) -> object:
    # No auth, no API key, no browser User-Agent required (verified). Plain stdlib.
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.load(r)


def main() -> None:
    cancers = {c["id"]: c for c in get("/meta/cancers/all/")}
    print(f"meta/cancers: {len(cancers)} sites returned (open, application/json)\n")

    # pull one rate payload per country, index by (cancer, sex=both, type)
    tables = {}
    for name, code in COUNTRIES.items():
        ds = get(f"/data/rate/0_1_2/0_1_2/{code}/all/{QS}")["dataset"]
        tables[name] = {(r["cancer_code"], r["sex"], r["type"]): r for r in ds}
        print(f"data/rate {name:15} pop={code}: {len(ds)} rows")
    print()

    hdr = f"{'target':30} {'site':34} {'match':6} " + " ".join(f"{c[:9]:>19}" for c in COUNTRIES)
    print(hdr)
    print(f"{'':30} {'':34} {'':6} " + " ".join(f"{'inc/mort ASR':>19}" for _ in COUNTRIES))
    for tname, (ccode, label, match) in TARGETS.items():
        cells = []
        for cname in COUNTRIES:
            inc = tables[cname].get((ccode, 0, 0))
            mort = tables[cname].get((ccode, 0, 1))
            i = inc["asr"] if inc else None
            m = mort["asr"] if mort else None
            cells.append(f"{str(i):>8}/{str(m):<9}")
        tag = match.split(":")[0]
        print(f"{tname:30} {label:34} {tag:6} " + " ".join(cells))

    print("\nASR = age-standardised rate per 100,000 (World standard). "
          "inc=incidence(type 0)  mort=mortality(type 1). sex=both.")


if __name__ == "__main__":
    main()
