"""Seed the target catalog from the target landscapes we already hold.

The target entity's universe is not "every human gene" (~20k, most irrelevant) but the
targets that already matter to this tool: the genes that appear in a cancer's target
landscape. Those rows already carry the two things the catalog needs -- the stable Ensembl
id and the approved symbol, both originally from Open Targets -- so the seed reads them
straight out of `cancer_fact`, no network call, fully deterministic. Every seeded target is
cancer-relevant by construction (it came from a cancer's landscape), so there is nothing to
prune.

`name` and `n_cancers` are left NULL: enrich_target (Phase 2) fills them via the reverse
Open Targets query. This loader only establishes which targets exist and what they are
called.

Run:  uv run python -m backend.ingestion.backfill_target_catalog [--only-missing]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.models import Target
from backend.repositories.targets import TargetRepository

logger = logging.getLogger(__name__)

# Distinct (ensembl_id, symbol) across every cancer's stored target landscape. DISTINCT ON
# with a matching ORDER BY picks one symbol per id (they agree in practice -- both are OT's
# approvedSymbol for the same gene -- but the symbol tiebreak makes the pick deterministic,
# the lexically-smallest, rather than whatever the planner returns first, should two cancers
# ever disagree). Only 'ok' facts, and only rows that actually carry both fields, so a
# source_failed or empty landscape contributes nothing.
_EXTRACT = text(
    """
    SELECT DISTINCT ON (elem ->> 'ensembl_id')
           elem ->> 'ensembl_id' AS ensembl_id,
           elem ->> 'symbol'     AS symbol
    FROM cancer_fact
    CROSS JOIN LATERAL jsonb_array_elements(cancer_fact.value -> 'targets') AS t(elem)
    WHERE cancer_fact.key = 'target_landscape'
      AND cancer_fact.status = 'ok'
      AND jsonb_typeof(cancer_fact.value -> 'targets') = 'array'
      AND elem ->> 'ensembl_id' IS NOT NULL
      AND elem ->> 'symbol' IS NOT NULL
    ORDER BY elem ->> 'ensembl_id', elem ->> 'symbol'
    """
)


@dataclass
class BackfillStats:
    landscape_targets: int = 0
    loaded: int = 0
    skipped_existing: int = 0

    def report(self) -> str:
        lines = [
            f"  distinct targets in landscapes : {self.landscape_targets}",
            f"  upserted into `target`         : {self.loaded}",
        ]
        if self.skipped_existing:
            lines.append(f"  skipped (already present)      : {self.skipped_existing}")
        return "\n".join(lines)


async def backfill_target_catalog(
    session: AsyncSession, *, only_missing: bool = False
) -> BackfillStats:
    """Load the target catalog from the stored cancer target landscapes.

    Idempotent: the upsert refreshes the symbol in place (it is OT's approvedSymbol either
    way), so a re-run is safe. --only-missing skips ids already present -- useful once
    enrich_target has filled name/n_cancers and a plain re-run would needlessly touch them.
    """
    stats = BackfillStats()
    repo = TargetRepository(session)

    rows = (await session.execute(_EXTRACT)).all()
    stats.landscape_targets = len(rows)

    existing: set[str] = set()
    if only_missing:
        existing = set((await session.execute(select(Target.ensembl_id))).scalars().all())

    for ensembl_id, symbol in rows:
        if only_missing and ensembl_id in existing:
            stats.skipped_existing += 1
            continue
        await repo.upsert_target(ensembl_id, symbol=symbol)
        stats.loaded += 1

    await session.commit()
    logger.info("target catalog: %d loaded, %d skipped", stats.loaded, stats.skipped_existing)
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="load only targets not already in the catalog (leaves enriched rows untouched)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        stats = await backfill_target_catalog(session, only_missing=args.only_missing)

    print("\n=== target catalog backfill ===")
    print(stats.report())


if __name__ == "__main__":
    asyncio.run(main())
