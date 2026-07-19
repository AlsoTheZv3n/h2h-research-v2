#!/usr/bin/env python3
"""S5 -- Modality & mRNA vaccines: is the category even in the catalog? THROWAWAY.

Probe A: distinct drug_type values + counts (is it granular enough to separate modalities?).
Probe B: are BNT111 / BNT116 / mRNA-4157 / autogene cevumeran in the catalog?
Asymmetry: for the absent ones, do CT.gov trials exist (surface via trial-reality, not as a drug)?

Run:  DATABASE_URL=postgresql+asyncpg://h2h:h2h@localhost:5433/h2h uv run python s5_modality_vaccines.py
"""
from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request

from sqlalchemy import text

from backend.db import get_sessionmaker

CT = "https://clinicaltrials.gov/api/v2/studies"
UA = "python-httpx/0.27 (h2h-spike-backlog; research)"


def ct_count(intr: str) -> int:
    p = {"query.intr": intr, "countTotal": "true", "pageSize": 1,
         "fields": "protocolSection.identificationModule.nctId"}
    req = urllib.request.Request(CT + "?" + urllib.parse.urlencode(p), headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=60)).get("totalCount")


async def main() -> None:
    async with get_sessionmaker()() as s:
        print("=== Probe A: drug_type distribution ===")
        for dt, c in (await s.execute(text(
            "SELECT COALESCE(drug_type,'(null)') dt, count(*) c FROM drug GROUP BY dt ORDER BY c DESC"
        ))).all():
            print(f"  {c:6}  {dt}")

        print("\n=== Probe B: the four named cancer mRNA vaccines ===")
        for name in ["BNT111", "BNT116", "mRNA-4157", "autogene cevumeran"]:
            rows = (await s.execute(text(
                "SELECT chembl_id, pref_name, drug_type FROM drug WHERE pref_name ILIKE :q"
            ), {"q": f"%{name}%"})).all()
            print(f"  {name:20} {rows if rows else 'ABSENT'}")

    print("\n=== Asymmetry: CT.gov trials for the catalog-absent vaccines ===")
    for v in ["BNT111", "BNT116", "mRNA-4157"]:
        print(f"  {v:12} CT.gov trials: {ct_count(v)}")


if __name__ == "__main__":
    asyncio.run(main())
