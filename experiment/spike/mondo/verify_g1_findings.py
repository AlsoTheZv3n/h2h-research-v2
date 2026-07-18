"""Throwaway: verify the two serious Gate-1 mapping findings live against Open Targets.

Finding 1 (brain/CNS): does GBM roll up to the current node MONDO_0001657, or only to the
proposed MONDO_0002714 (CNS cancer)?
Finding 2 (uterine): does uterine carcinosarcoma roll up to the current node MONDO_0011962
(endometrial), or only to the proposed MONDO_0002715 (uterine cancer)? And how does the
proposed node interact with cervix (C53) under closest-wins?
"""

from __future__ import annotations

import json
import urllib.request

OT = "https://api.platform.opentargets.org/api/v4/graphql"
Q = """query D($id: String!) {
  disease(efoId: $id) { id name ancestors descendants }
}"""

IDS = {
    "MONDO_0001657": "brain cancer (CURRENT brain node)",
    "MONDO_0002714": "CNS cancer? (PROPOSED brain node)",
    "MONDO_0018177": "glioblastoma",
    "MONDO_0005499": "brain glioma",
    "MONDO_0021042": "glioma",
    "MONDO_0011962": "endometrial cancer (CURRENT uterine node)",
    "MONDO_0002715": "uterine cancer? (PROPOSED uterine node)",
    "MONDO_0006485": "uterine carcinosarcoma",
    "MONDO_0002974": "cervical cancer (C53)",
}


def fetch(mondo: str) -> dict:
    body = json.dumps({"query": Q, "variables": {"id": mondo}}).encode()
    req = urllib.request.Request(
        OT, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["disease"]


def has(container: dict | None, mondo: str) -> str:
    if container is None:
        return "NULL-DISEASE"
    a = set(container.get("ancestors") or [])
    d = set(container.get("descendants") or [])
    return f"anc={'Y' if mondo in a else '-'} desc={'Y' if mondo in d else '-'}"


data = {mid: fetch(mid) for mid in IDS}
for mid, label in IDS.items():
    name = data[mid]["name"] if data[mid] else "??"
    print(f"{mid}  {name!r}  [{label}]")

print("\n--- FINDING 1: brain/CNS ---")
print(f"GBM anc contains CURRENT brain MONDO_0001657? {has(data['MONDO_0018177'], 'MONDO_0001657')}")
print(f"GBM anc contains PROPOSED CNS  MONDO_0002714? {has(data['MONDO_0018177'], 'MONDO_0002714')}")
print(f"brain(0001657) anc contains PROPOSED CNS 0002714? {has(data['MONDO_0001657'], 'MONDO_0002714')}")
print(f"glioma(0021042) anc contains PROPOSED CNS 0002714? {has(data['MONDO_0021042'], 'MONDO_0002714')}")
print(f"brain glioma(0005499) anc contains CNS 0002714? {has(data['MONDO_0005499'], 'MONDO_0002714')}")

print("\n--- FINDING 2: uterine ---")
print(f"carcinosarcoma anc contains CURRENT endometrial 0011962? {has(data['MONDO_0006485'], 'MONDO_0011962')}")
print(f"carcinosarcoma anc contains PROPOSED uterine 0002715? {has(data['MONDO_0006485'], 'MONDO_0002715')}")
print(f"endometrial(0011962) anc contains PROPOSED uterine 0002715? {has(data['MONDO_0011962'], 'MONDO_0002715')}")
print(f"cervix(0002974) anc contains PROPOSED uterine 0002715? {has(data['MONDO_0002974'], 'MONDO_0002715')}")
