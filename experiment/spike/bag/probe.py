#!/usr/bin/env python3
"""Phase 0 data spike -- BAG Spezialitätenliste (Swiss reimbursed-drug list + prices).

THROWAWAY probe. Stdlib only (urllib + json) -- no new deps, runs anywhere.
Makes REAL calls to the public SL API and measures, per cancer, whether an
on-label oncology drug's Swiss list price is retrievable openly.

Access facts established by this probe:
  * NO login, NO API key. Plain GET returns JSON.
  * The SL is NOT published on opendata.swiss (search -> 0 hits). It is served
    by the JSON backend of the official webapp: https://epl.bag.admin.ch/api/sl/
  * A Windows/Chrome User-Agent is needed; a bare/default UA is 403'd by the WAF
    on the *.admin.ch edge (same class of block seen on www.admin.ch terms page).

COVERAGE == would a "Swiss list price" evidence block render POPULATED, per cancer.
Measured here as: does a real on-label drug return exFactoryPrice / retailPrice
(both CHF) for at least one pack.

None != 0: a drug we could not reach is "not measured", never "price 0".
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.request
from pathlib import Path

API = "https://epl.bag.admin.ch/api/sl/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
OUT = Path(__file__).with_name("out")
OUT.mkdir(exist_ok=True)
_CTX = ssl.create_default_context()

# search term -> (cancer, on-label agent)
CANCERS = {
    "Tagrisso":  ("NSCLC",                "osimertinib"),
    "Herceptin": ("breast carcinoma",     "trastuzumab"),
    "Tafinlar":  ("melanoma",             "dabrafenib"),
    "Glivec":    ("CML",                  "imatinib"),
    "Abraxane":  ("pancreatic carcinoma", "nab-paclitaxel (+gemcitabine)"),
}


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=_CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def strip_html(s: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def first_priced_pack(payload: dict):
    """Return (trademark, dosage, packSize, exFactory, retail, itCode, indication)
    for the first pack that carries a real CHF price, or None if none present."""
    for item in payload.get("items", []):
        for mp in item.get("medicinalProducts", []):
            itc = (mp.get("itCode") or {})
            ind = ""
            for lim in mp.get("limitations", []):
                ind = strip_html(lim.get("description"))[:180]
                if ind:
                    break
            for pk in mp.get("packagedMedicinalProducts", []):
                exf, ret = pk.get("exFactoryPrice"), pk.get("retailPrice")
                if exf is not None or ret is not None:
                    return (item.get("trademark"), mp.get("dosageFormAndStrength"),
                            pk.get("packSize"), exf, ret,
                            f'{itc.get("code")} {itc.get("description")}', ind)
    return None


def main() -> None:
    # Access proof: SL absent from opendata.swiss.
    ods = get("https://ckan.opendata.swiss/api/3/action/"
              "package_search?q=Spezialit%C3%A4tenliste&rows=5")
    print(f"opendata.swiss 'Spezialitätenliste' hits: {ods['result']['count']} "
          f"(SL is NOT an opendata.swiss dataset)\n")

    print(f"{'cancer':22} {'drug':24} {'pack':14} {'exFactory':>10} {'retail':>9}  state")
    print("-" * 96)
    populated = 0
    rows = []
    for term, (cancer, agent) in CANCERS.items():
        payload = get(f"{API}public/medicinal-products?page=1&size=20&search={term}")
        (OUT / f"search_{term}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        hit = first_priced_pack(payload)
        if hit:
            tm, dose, pack, exf, ret, itc, ind = hit
            populated += 1
            state = "POPULATED"
            print(f"{cancer:22} {tm+' '+(dose or ''):24.24} {pack or '':14.14} "
                  f"{exf if exf is not None else '-':>10} {ret if ret is not None else '-':>9}  {state}")
            rows.append((cancer, agent, tm, dose, pack, exf, ret, itc, ind))
        else:
            # EMPTY = source answered, no priced pack. None-state (unreachable) would raise above.
            print(f"{cancer:22} {'('+agent+')':24.24} {'':14} {'':>10} {'':>9}  EMPTY (no priced pack)")
            rows.append((cancer, agent, None, None, None, None, None, None, ""))

    print("-" * 96)
    print(f"COVERAGE: {populated}/{len(CANCERS)} cancers POPULATED with a real CHF list price\n")

    print("On-label indication text confirming each drug treats its cancer (SL limitation):")
    for cancer, agent, tm, dose, pack, exf, ret, itc, ind in rows:
        if ind:
            print(f"  [{cancer}] {tm}: {ind[:120]}")


if __name__ == "__main__":
    main()
