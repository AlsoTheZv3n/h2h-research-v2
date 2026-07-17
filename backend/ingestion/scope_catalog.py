"""Soft-scope the catalog: mark non-oncology false positives, never delete them.

The catalog is built by substring-matching disease terms (see chembl_catalog), which
pulls in drugs whose cancer link is incidental -- an approved statin or contrast agent
with one exploratory "Neoplasms" trial. This pass re-reads each drug's ChEMBL
indications and sets `in_scope`:

  True   a real oncology programme
  False  a blunt-only match that trails the drug's real development -> hidden by default

Nothing is deleted. `in_scope` is reversible: re-running with a tuned rule, or clearing
the column, restores a drug. Rows it never reaches stay NULL, which the overview shows --
so an interrupted or incomplete pass hides nothing it did not positively judge.

Two safeguards make this safe to run:
  --dry-run  reports what WOULD be excluded, writes nothing
  a fixed set of known oncology drugs is checked every run; if the rule would exclude
  any of them, that is a loud failure -- the rule is too aggressive, not the drug wrong

Run:  uv run python -m backend.ingestion.scope_catalog --dry-run   # look first
      uv run python -m backend.ingestion.scope_catalog             # apply
      uv run python -m backend.ingestion.scope_catalog --reevaluate  # re-judge all rows
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.ingestion.chembl_catalog import BASE, _get_json, is_out_of_scope
from backend.ingestion.http import build_client
from backend.models import Drug
from backend.repositories import DrugRepository

logger = logging.getLogger(__name__)

_CONCURRENCY = 6

# Drugs whose oncology status is not in question. If the rule would ever exclude one of
# these, the rule is wrong -- so every run checks them and refuses to read as clean if
# any is flagged. Well-known approved oncology drugs across modalities and targets.
KNOWN_ONCOLOGY: dict[str, str] = {
    "CHEMBL3353410": "osimertinib",
    "CHEMBL4535757": "sotorasib",
    "CHEMBL4594350": "adagrasib",
    "CHEMBL941": "imatinib",
    "CHEMBL1201585": "trastuzumab",
    "CHEMBL1201583": "rituximab",
    "CHEMBL288441": "erlotinib",
    "CHEMBL1201247": "bevacizumab",
    "CHEMBL3137343": "pembrolizumab",
    "CHEMBL2108738": "palbociclib",
}


@dataclass
class ScopeStats:
    evaluated: int = 0
    kept: int = 0
    excluded: int = 0
    fetch_failed: int = 0
    excluded_examples: list[str] = field(default_factory=list)
    known_wrongly_excluded: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"  evaluated              : {self.evaluated}",
            f"  kept in scope          : {self.kept}",
            f"  marked out of scope    : {self.excluded}",
        ]
        if self.fetch_failed:
            lines.append(f"  fetch failed (left as-is): {self.fetch_failed}")
        if self.excluded_examples:
            lines.append("  out-of-scope examples:")
            lines += [f"    - {e}" for e in self.excluded_examples[:15]]
        if self.known_wrongly_excluded:
            lines.append("")
            lines.append(
                "  !! KNOWN ONCOLOGY DRUGS the rule would EXCLUDE -- rule is too aggressive:"
            )
            lines += [f"    - {e}" for e in self.known_wrongly_excluded]
            lines.append("  !! Do not apply this pass until the rule keeps them.")
        return "\n".join(lines)


async def _indications(client: httpx.AsyncClient, chembl_id: str) -> list[dict[str, Any]] | None:
    """Every drug_indication row for one molecule, or None if ChEMBL could not answer.

    Per-molecule, not batched: "zero rows" then unambiguously means "this drug has no
    indication", which the classifier needs to tell a genuine non-oncology drug from one
    ChEMBL merely dropped from a mixed batch. A high limit because a page boundary that
    split off a drug's only cancer row would misjudge it.
    """
    body = await _get_json(
        client, f"{BASE}/drug_indication.json", {"molecule_chembl_id": chembl_id, "limit": 1000}
    )
    if body is None:
        return None
    return list(body.get("drug_indications", []))


async def scope_catalog(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    reevaluate: bool = False,
) -> ScopeStats:
    if client is None:
        async with build_client() as owned:
            return await scope_catalog(
                session, client=owned, limit=limit, dry_run=dry_run, reevaluate=reevaluate
            )

    stats = ScopeStats()
    repo = DrugRepository(session)

    query = select(Drug).order_by(Drug.chembl_id)
    if not reevaluate:
        # Resumable: only rows not yet judged. A crash-and-restart resumes, and a re-run
        # after a full pass is a no-op -- in_scope IS NULL is the bookmark.
        query = query.where(Drug.in_scope.is_(None))
    if limit:
        query = query.limit(limit)
    drugs = list((await session.execute(query)).scalars().all())
    logger.info("scoping %d drugs%s", len(drugs), " (dry run)" if dry_run else "")

    for i in range(0, len(drugs), _CONCURRENCY):
        wave = drugs[i : i + _CONCURRENCY]
        rows_per = await asyncio.gather(*(_indications(client, d.chembl_id) for d in wave))
        for drug, rows in zip(wave, rows_per, strict=True):
            if rows is None:
                stats.fetch_failed += 1
                continue
            out = is_out_of_scope(rows, drug.max_phase)
            # The known list is a hard override, not just a warning: a well-known
            # oncology drug is never excluded, whatever the rule says. If the rule and
            # the list disagree, that is recorded loudly -- it means the rule drifted
            # and needs tightening, but no known drug is hidden in the meantime.
            if out and drug.chembl_id in KNOWN_ONCOLOGY:
                stats.known_wrongly_excluded.append(
                    f"{KNOWN_ONCOLOGY[drug.chembl_id]} ({drug.chembl_id})"
                )
                out = False
            stats.evaluated += 1
            if out:
                stats.excluded += 1
                if len(stats.excluded_examples) < 15:
                    name = drug.pref_name or drug.chembl_id
                    stats.excluded_examples.append(
                        f"{name} ({drug.chembl_id}, phase {drug.max_phase})"
                    )
            else:
                stats.kept += 1
            if not dry_run:
                await repo.upsert_drug(drug.chembl_id, in_scope=not out)
        if not dry_run:
            await session.commit()
            logger.info("committed: %d evaluated so far", stats.evaluated)

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Soft-scope the oncology catalog.")
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument("--limit", type=int, help="only the first N drugs")
    parser.add_argument(
        "--reevaluate", action="store_true", help="re-judge every row, not just unscored ones"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    async with get_sessionmaker()() as session:
        stats = await scope_catalog(
            session, limit=args.limit, dry_run=args.dry_run, reevaluate=args.reevaluate
        )

    print(f"\n=== catalog scoping{' (DRY RUN -- nothing written)' if args.dry_run else ''} ===")
    print(stats.report())


if __name__ == "__main__":
    asyncio.run(main())
