"""Backfill the drug_target relation for drugs enriched before it existed.

The drug->target relation (by Ensembl id) is populated on enrichment from Open Targets
(see enrich._promote), so drugs enriched before it was added have no rows -- and the
cancer target landscape's catalog-link would read "no drug in our catalog against this
target" for targets we actually do hold a drug against. Re-running the full four-source
enrichment would work but re-fetches structure, trials and abstracts we already have; this
asks Open Targets alone for each drug's target Ensembl ids, writes the `target_ids`
provenance fact, and syncs drug_target -- nothing else.

Idempotent and resumable like enrich_catalog: it selects only enriched drugs that have no
`target_ids` fact yet, so the fact doubles as the "done" marker -- a crash-and-restart
resumes where it left off, a re-run over a filled catalog is a no-op, and a drug whose
mechanisms carry no target gets an EMPTY target_ids fact (marked done, no drug_target rows)
rather than being retried forever.

Run:  uv run python -m backend.ingestion.backfill_drug_targets
      uv run python -m backend.ingestion.backfill_drug_targets --limit 20
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
from backend.models import Drug, FactRow
from backend.repositories import DrugRepository

logger = logging.getLogger(__name__)


async def backfill(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int | None = None,
) -> tuple[int, int]:
    """Populate drug_target from Open Targets for enriched drugs that lack a target_ids fact.

    Returns (candidates seen, drugs synced). The gap is drugs Open Targets did not resolve
    this run -- left for the next, never marked done on an outage.
    """
    if client is None:
        async with build_client() as owned:
            return await backfill(session, client=owned, limit=limit)

    repo = DrugRepository(session)
    # Enriched drugs with no target_ids fact yet -- the fact is the "done" marker, so this
    # skips anything already backfilled and resumes cleanly after a crash.
    done = select(FactRow.drug_chembl_id).where(FactRow.key == "target_ids")
    query = (
        select(Drug)
        .where(Drug.last_enriched_at.isnot(None))
        .where(Drug.chembl_id.notin_(done))
        .order_by(Drug.chembl_id)
    )
    if limit:
        query = query.limit(limit)
    drugs = list((await session.execute(query)).scalars().all())
    logger.info("backfilling drug_target for %d drugs", len(drugs))

    adapter = OpenTargetsAdapter(client)
    synced = 0
    for drug in drugs:
        record = await adapter.fetch(drug.pref_name or drug.chembl_id)
        tf = record.facts.get("target_ids")
        if tf is None:
            # Open Targets did not resolve (outage or no hit) -- leave for the next run
            # rather than marking it done with an empty set we cannot stand behind.
            logger.info("%s: Open Targets did not resolve; leaving for next run", drug.chembl_id)
            continue

        # Persist the fact whatever its status -- an EMPTY "no targets" is a real answer and
        # marks the drug done, so a re-run skips it instead of re-fetching forever.
        await repo.save_record(
            drug.chembl_id,
            SourceRecord(
                adapter.name,
                record.query,
                ok=True,
                facts={"target_ids": tf},
                provenance=record.provenance,
            ),
        )
        # Only a non-failed fact reaches sync (the fetch above already returns no target_ids
        # on outage), so a wiped set here always means the measured "these are the targets".
        if tf.status is not FactStatus.SOURCE_FAILED:
            await repo.sync_drug_targets(drug.chembl_id, tf.value or [])
            synced += 1
        await session.commit()

    return len(drugs), synced


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill drug_target from Open Targets.")
    parser.add_argument("--limit", type=int, help="only the first N candidates")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    async with get_sessionmaker()() as session:
        seen, synced = await backfill(session, limit=args.limit)

    print(f"\n=== drug_target backfill ===\n  candidates: {seen}\n  drugs synced: {synced}")


if __name__ == "__main__":
    asyncio.run(main())
