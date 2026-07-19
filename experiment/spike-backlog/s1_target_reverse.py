#!/usr/bin/env python3
"""S1 -- Target page: does Open Targets go backwards (target -> associated diseases)? THROWAWAY.

Confirm the reverse field exists, returns SCORES, and returns disease IDs (EFO/MONDO) -- not just
labels. Then measure how many of those disease IDs JOIN to our cancer catalog by ID.

Run:  DATABASE_URL=... uv run python s1_target_reverse.py
"""
from __future__ import annotations

import asyncio
import json
import urllib.request

from sqlalchemy import text

from backend.db import get_sessionmaker

OT = "https://api.platform.opentargets.org/api/v4/graphql"
TARGETS = {"EGFR": "ENSG00000146648", "KRAS": "ENSG00000133703", "BRCA1": "ENSG00000012048"}

Q = """query T($id: String!, $n: Int!) {
  target(ensemblId: $id) {
    id approvedSymbol
    associatedDiseases(page: {index: 0, size: $n}) {
      count
      rows { score disease { id name } }
    }
  }
}"""


def gql(query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        OT, data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"content-type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=60))["data"]


async def main() -> None:
    async with get_sessionmaker()() as s:
        catalog = {r[0] for r in (await s.execute(text("SELECT disease_id FROM cancer"))).all()}
    print(f"cancer catalog: {len(catalog)} disease ids\n")
    for sym, ens in TARGETS.items():
        t = gql(Q, {"id": ens, "n": 50})["target"]
        ad = t["associatedDiseases"]
        rows = ad["rows"]
        # confirm shape: score present, disease.id present (an EFO/MONDO id, not a label)
        has_scores = all(isinstance(r.get("score"), (int, float)) for r in rows)
        ids = [r["disease"]["id"] for r in rows if r.get("disease")]
        id_shaped = sum(1 for i in ids if i and ("_" in i))  # MONDO_/EFO_/... look
        in_catalog = [i for i in ids if i in catalog]
        print(f"{sym} ({ens}): total associated = {ad['count']}, fetched top {len(rows)}")
        print(f"  scores present on all fetched rows: {has_scores}")
        print(f"  disease IDs id-shaped (EFO/MONDO): {id_shaped}/{len(ids)}")
        print(f"  of the fetched top {len(ids)}, JOIN to cancer catalog by ID: {len(in_catalog)}")
        print(f"  sample joined: {in_catalog[:5]}")
        print(f"  top-3 by score: {[(round(r['score'],2), r['disease']['id'], r['disease']['name']) for r in rows[:3]]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
