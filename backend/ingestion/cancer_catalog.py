"""Bulk-load the oncology cancer catalog from Open Targets.

The disease spine for the whole expansion. Open Targets is the one source that carries
a stable disease ontology (MONDO/EFO) alongside per-disease association and drug-
candidate counts, it is CC0, and -- unlike ChEMBL, which the drug catalog has to nurse
through constant 500s -- it answers reliably, so this loads cleanly in one pass.

We seed only cancers with a real hit: at least one drug/clinical candidate OR one
associated target. The 'cancer' ontology root has 1,744 descendants, and a quarter of
them carry no evidence at all (organ-system rollups like "respiratory system cancer",
ultra-rare subtypes with nothing attached). A catalog row that renders every block
empty is not a feature -- so those are counted and dropped, not listed.

Both counts are kept as index columns, so the overview can rank by therapeutic
activity and narrow to "has a drug programme" without re-querying the source.

Run:  uv run python -m backend.ingestion.cancer_catalog
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.ingestion.http import build_client
from backend.models import Cancer
from backend.repositories.cancers import CancerRepository

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"

# The MONDO root of the cancer branch; its descendants are the oncology universe
# (1,744 in the 26.06 release). The old EFO cancer root (EFO_0000311) now resolves to
# null -- the platform migrated disease ids EFO -> MONDO, silently, which is why every
# legacy EFO id in the spike read empty. Key on MONDO.
CANCER_ROOT = "MONDO_0004992"

# The generic top area every cancer carries. Useless as a facet on its own, so a more
# specific organ-system area is preferred when the disease has one.
_GENERIC_AREA = "cancer or benign tumor"

# Open Targets answers a 50-alias batch comfortably. Modest concurrency: it is a shared
# public service, and the point is to finish in a sitting, not to hammer it.
_BATCH = 50
_CONCURRENCY = 4

# One disease, aliased so a batch of them rides in a single GraphQL document. `efoId`
# is the (legacy-named) arg that accepts any disease id, MONDO included. A size-1
# associatedTargets page is enough: we read `count`, not the rows.
_DISEASE_FRAGMENT = (
    'd{i}:disease(efoId:"{id}"){{ id name therapeuticAreas{{ name }} '
    "drugs:drugAndClinicalCandidates{{ count }} "
    "targets:associatedTargets(page:{{index:0,size:1}}){{ count }} }}"
)


@dataclass
class LoadStats:
    descendants: int = 0
    resolved: int = 0
    loaded: int = 0
    pruned: int = 0
    batches_failed: int = 0

    def report(self) -> str:
        lines = [
            f"  descendants of {CANCER_ROOT} : {self.descendants}",
            f"  resolved by Open Targets     : {self.resolved}",
            f"  loaded into `cancer`         : {self.loaded}",
            f"  pruned (no drug, no target)  : {self.pruned}",
        ]
        if self.batches_failed:
            # Never let a partial load read as a complete one.
            lines.append(
                f"  !! batches lost              : {self.batches_failed} (catalog incomplete)"
            )
            lines.append("  NOTE: this run is a FLOOR. Re-run with --only-missing to fill gaps.")
        return "\n".join(lines)


async def _gql(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    """POST a GraphQL query, surfacing the `errors` array like the OT adapter does.

    A 200-with-errors partial failure would otherwise yield null fields with no error
    -- the exact blind spot the drug adapter's _gql closed. Same handling here.
    """
    r = await client.post(ENDPOINT, json={"query": query})
    body: dict[str, Any] | None = None
    try:
        body = r.json()
    except ValueError:
        body = None  # a 502 HTML page: fall through to raise_for_status below
    if body and body.get("errors"):
        raise RuntimeError("; ".join(e.get("message", "") for e in body["errors"]))
    r.raise_for_status()
    return (body or {}).get("data") or {}


async def fetch_descendants(client: httpx.AsyncClient) -> list[str]:
    """Every disease id under the cancer root, in one call."""
    data = await _gql(client, f'{{ disease(efoId:"{CANCER_ROOT}") {{ descendants }} }}')
    disease = data.get("disease") or {}
    return list(disease.get("descendants") or [])


async def fetch_batch(client: httpx.AsyncClient, ids: list[str]) -> list[dict[str, Any]]:
    """Resolve a batch of disease ids to their catalog fields.

    A disease id that no longer resolves comes back null and is simply dropped -- an
    obsolete descendant, not an error.
    """
    frag = " ".join(_DISEASE_FRAGMENT.format(i=i, id=did) for i, did in enumerate(ids))
    data = await _gql(client, "{" + frag + "}")
    out = []
    for i in range(len(ids)):
        d = data.get(f"d{i}")
        if d and d.get("id"):
            out.append(d)
    return out


def pick_therapeutic_area(areas: list[dict[str, Any]] | None) -> str | None:
    """The organ-system area to facet on: a specific one over the generic cancer area."""
    names: list[str] = [a["name"] for a in (areas or []) if a.get("name")]
    specific = [n for n in names if n.lower() != _GENERIC_AREA]
    if specific:
        return specific[0]
    return names[0] if names else None


def to_columns(disease: dict[str, Any]) -> dict[str, Any]:
    """Map an Open Targets disease onto the catalog's index columns."""
    return {
        "name": disease.get("name") or disease.get("id"),
        "therapeutic_area": pick_therapeutic_area(disease.get("therapeuticAreas")),
        "n_drugs": int((disease.get("drugs") or {}).get("count") or 0),
        "n_targets": int((disease.get("targets") or {}).get("count") or 0),
    }


def is_real_hit(columns: dict[str, Any]) -> bool:
    """A cancer earns a catalog row if it has a drug programme OR an associated target.

    The chosen scope: comprehensive across evidence, but not the ~24% of descendants
    with neither -- rollup nodes and ultra-rare subtypes that would render every block
    empty. `has_drugs` in the overview narrows this further to just the drugged ones.
    """
    return bool(columns["n_drugs"] > 0 or columns["n_targets"] > 0)


async def load_catalog(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    only_missing: bool = False,
) -> LoadStats:
    """Load the cancer catalog from Open Targets.

    Commits per wave so a lost batch (or a Ctrl-C) leaves what already landed in place,
    and --only-missing then fills the rest -- resumable, like the drug loader.
    """
    if client is None:
        async with build_client() as owned:
            return await load_catalog(session, client=owned, only_missing=only_missing)

    stats = LoadStats()
    repo = CancerRepository(session)

    ids = await fetch_descendants(client)
    stats.descendants = len(ids)

    if only_missing:
        existing = set((await session.execute(select(Cancer.disease_id))).scalars().all())
        ids = [i for i in ids if i not in existing]
        logger.info("only-missing: %d of %d still to resolve", len(ids), stats.descendants)

    batches = [ids[i : i + _BATCH] for i in range(0, len(ids), _BATCH)]
    for i in range(0, len(batches), _CONCURRENCY):
        wave = batches[i : i + _CONCURRENCY]
        # return_exceptions so one failed batch is recorded and skipped, never fatal --
        # the run stays resumable rather than all-or-nothing.
        results = await asyncio.gather(
            *(fetch_batch(client, b) for b in wave), return_exceptions=True
        )
        for res in results:
            if isinstance(res, BaseException):
                stats.batches_failed += 1
                logger.warning("cancer batch failed: %s", str(res)[:120])
                continue
            for disease in res:
                stats.resolved += 1
                columns = to_columns(disease)
                if not is_real_hit(columns):
                    stats.pruned += 1
                    continue
                await repo.upsert_cancer(disease["id"], **columns)
                stats.loaded += 1
        await session.commit()
        logger.info("cancer catalog: %d loaded, %d pruned so far", stats.loaded, stats.pruned)

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="resolve only descendants not already in the catalog (fills gaps after a lost batch)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        stats = await load_catalog(session, only_missing=args.only_missing)

    print("\n=== Open Targets cancer catalog ===")
    print(stats.report())


if __name__ == "__main__":
    asyncio.run(main())
