"""Backfill target_class for drugs enriched before the column existed.

target_class arrives with enrichment, from Open Targets (see enrich._promote). Drugs
enriched before this column was added therefore have it NULL, and the overview's
target-class facet is empty for them. Re-running the full four-source enrichment would
work, but it re-fetches structure, trials and abstracts we already hold and re-stamps
last_enriched_at -- so this asks Open Targets alone and writes the one column and its
provenance fact, nothing else.

Idempotent and resumable, the same way enrich_catalog is: it selects only rows that
have a target but no class yet, so a crash-and-restart resumes exactly where it left
off and a re-run over a filled catalog is a no-op. A target with no class in Open
Targets stays NULL and is retried next run -- an EMPTY answer is not persisted as a
class, which would be the None-vs-value confusion this codebase exists to avoid.

Run:  uv run python -m backend.ingestion.backfill_target_class
      uv run python -m backend.ingestion.backfill_target_class --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.ingestion.base import FactStatus, SourceRecord
from backend.ingestion.http import build_client
from backend.ingestion.opentargets import OpenTargetsAdapter
from backend.models import Drug
from backend.repositories import DrugRepository

logger = logging.getLogger(__name__)


async def backfill(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int | None = None,
) -> tuple[int, int]:
    """Fill target_class from Open Targets for rows that have a target but no class.

    Returns (candidates seen, classes written). The gap between them is the drugs whose
    target Open Targets carries no class for -- left NULL on purpose, not filled with a
    placeholder.
    """
    if client is None:
        async with build_client() as owned:
            return await backfill(session, client=owned, limit=limit)

    repo = DrugRepository(session)
    query = select(Drug).where(Drug.primary_target.isnot(None), Drug.target_class.is_(None))
    if limit:
        query = query.limit(limit)
    drugs = list((await session.execute(query)).scalars().all())
    logger.info("backfilling target_class for %d drugs", len(drugs))

    adapter = OpenTargetsAdapter(client)
    written = 0
    for drug in drugs:
        record = await adapter.fetch(drug.pref_name or drug.chembl_id)
        tc = record.facts.get("target_class")
        if tc is None:
            # The source failed entirely (outage) -- leave the row for the next run.
            logger.info("%s: Open Targets did not resolve; leaving NULL", drug.chembl_id)
            continue

        # Persist the provenance fact whatever its status (an EMPTY "no class" is a
        # real answer worth recording), but only promote a value into the column.
        await repo.save_record(
            drug.chembl_id,
            SourceRecord(
                adapter.name,
                record.query,
                ok=True,
                facts={"target_class": tc},
                provenance=record.provenance,
            ),
        )
        if tc.status is FactStatus.OK and tc.value:
            # Write primary_target from the SAME fetch, so the class we store is the
            # class of the target we store -- Open Targets may have drifted since this
            # row was first enriched, and a class pinned to a stale primary_target would
            # be the very divergence this backfill must not create.
            columns: dict[str, object] = {"target_class": tc.value}
            targets = record.facts.get("targets")
            if targets is not None and targets.status is FactStatus.OK and targets.value:
                columns["primary_target"] = targets.value[0]
            await repo.upsert_drug(drug.chembl_id, **columns)
            written += 1
        await session.commit()

    return len(drugs), written


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill target_class from Open Targets.")
    parser.add_argument("--limit", type=int, help="only the first N candidates")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    async with get_sessionmaker()() as session:
        seen, written = await backfill(session, limit=args.limit)

    print(f"\n=== target_class backfill ===\n  candidates: {seen}\n  classes written: {written}")


if __name__ == "__main__":
    asyncio.run(main())
