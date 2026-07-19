#!/usr/bin/env python3
"""S2 -- Tissue-agnostic: does the metric separate the right drugs? THROWAWAY.

For each golden-set drug, take its Open Targets indications and walk MONDO ancestors (the Gate 1
walker) to count how many distinct ORGAN SYSTEMS its cancer indications span. Then test:
  positives (tissue-agnostic): pembrolizumab, T-DXd, larotrectinib, selpercatinib
  negatives (organ-bound):     osimertinib, abiraterone
  control (broad, NOT agnostic): bevacizumab   <-- the sharp test
A pure "organ span" metric measures BREADTH. The question: does it separate bevacizumab (broad
but not biomarker-agnostic) from the true tissue-agnostic drugs? If not, the badge would mean
"widely used", not "tissue-agnostic".

Run:  uv run python s2_tissue_agnostic.py
"""
from __future__ import annotations

import json
import urllib.request

OT = "https://api.platform.opentargets.org/api/v4/graphql"

GOLDEN = {
    "pembrolizumab": ("CHEMBL3137343", "positive"),
    "trastuzumab deruxtecan": ("CHEMBL4297844", "positive"),
    "larotrectinib": ("CHEMBL3889654", "positive"),
    "selpercatinib": ("CHEMBL4559134", "positive"),
    "osimertinib": ("CHEMBL3353410", "negative"),
    "abiraterone": ("CHEMBL254328", "negative"),
    "bevacizumab": ("CHEMBL1201583", "control-broad-not-agnostic"),
}

# Top-level organ-system anchors (major cancer sites). An indication counts toward an organ if
# that organ's MONDO node is the indication itself or one of its ancestors.
ANCHORS = {
    "MONDO_0008903": "lung", "MONDO_0007254": "breast", "MONDO_0005575": "colorectal",
    "MONDO_0005105": "skin/melanoma", "MONDO_0002714": "CNS", "MONDO_0008315": "prostate",
    "MONDO_0008170": "ovary", "MONDO_0009831": "pancreas", "MONDO_0002691": "liver",
    "MONDO_0002367": "kidney", "MONDO_0001056": "stomach", "MONDO_0001187": "bladder",
    "MONDO_0002108": "thyroid", "MONDO_0005627": "head&neck", "MONDO_0002715": "uterine",
    "MONDO_0002974": "cervix", "MONDO_0007576": "esophagus",
    # blood cancers collapse to one organ system
    "MONDO_0005059": "hematologic", "MONDO_0005062": "hematologic", "MONDO_0009693": "hematologic",
}


def gql(q: str, v: dict) -> dict:
    return json.load(urllib.request.urlopen(
        urllib.request.Request(OT, data=json.dumps({"query": q, "variables": v}).encode(),
                               headers={"content-type": "application/json"}), timeout=90))["data"]


def indications(chembl: str) -> list[str]:
    q = "query D($id:String!){drug(chemblId:$id){indications{rows{disease{id}}}}}"
    d = gql(q, {"id": chembl})["drug"]
    return [r["disease"]["id"] for r in (d["indications"]["rows"] if d else [])]


def ancestors_batch(ids: list[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        parts = [f'a{j}: disease(efoId:"{d}"){{id ancestors}}' for j, d in enumerate(chunk)]
        data = gql("{ " + " ".join(parts) + " }", {})
        for j, d in enumerate(chunk):
            node = data.get(f"a{j}")
            out[d] = set(node["ancestors"]) if node else set()
    return out


def organs(inds: list[str], anc: dict[str, set[str]]) -> set[str]:
    found: set[str] = set()
    for d in inds:
        for anchor, organ in ANCHORS.items():
            if d == anchor or anchor in anc.get(d, set()):
                found.add(organ)
    return found


def main() -> None:
    inds = {name: indications(cid) for name, (cid, _) in GOLDEN.items()}
    uniq = sorted({d for v in inds.values() for d in v})
    anc = ancestors_batch(uniq)
    print(f"{'drug':24} {'class':28} {'#ind':>5} {'organs':>7}  spanned")
    print("-" * 100)
    rows = []
    for name, (_, cls) in GOLDEN.items():
        orgs = organs(inds[name], anc)
        rows.append((name, cls, len(inds[name]), len(orgs), sorted(orgs)))
    for name, cls, n, span, orgs in sorted(rows, key=lambda r: -r[3]):
        print(f"{name:24} {cls:28} {n:5} {span:7}  {', '.join(orgs)}")


if __name__ == "__main__":
    main()
