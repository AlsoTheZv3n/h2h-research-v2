"""On-demand enrichment of a target's evidence brief.

The target-side twin of enrich_cancer.py. The catalog holds index columns only; a target's
real evidence -- which cancers it is associated with -- is fetched the first time someone
opens it and served from Postgres after.

The one source is the mirror of the cancer page's target landscape, run BACKWARDS: Open
Targets' `target(ensemblId){ associatedDiseases }`. That reverse query returns a target's
associated diseases, cancers AND non-cancers alike (KRAS's top hits are Noonan / RASopathy
syndromes, above any cancer), so the result is filtered to the diseases our catalog actually
lists -- by MONDO/EFO id, never by name. What survives is the cancers this target drives, each
a live link into its brief.

Run:  uv run python -m backend.ingestion.enrich_target --target ENSG00000146648
      uv run python -m backend.ingestion.enrich_target --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.ingestion.base import SourceRecord, fact, failed, utcnow
from backend.ingestion.http import build_client
from backend.models import Target
from backend.repositories.cancers import CancerRepository
from backend.repositories.targets import TargetRepository

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"

# The reverse of the cancer landscape query. approvedName fills the catalog's descriptive
# name; associatedDiseases is scored, so the scan comes back cancer-relevant-first.
_REVERSE_QUERY = """
query TargetCancers($id: String!, $n: Int!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    approvedName
    associatedDiseases(page: {index: 0, size: $n}) {
      count
      rows {
        score
        disease { id name }
      }
    }
  }
}
"""

# How many associated diseases to SCAN (score-descending) when filtering to our catalog. A
# target lists thousands of associations (EGFR ~6,500); the cancers we hold are the strongly
# associated ones, high in that order, so 600 covers them with headroom -- the same scan
# discipline the cancer target-landscape uses.
_SCAN_DISEASES = 600

# How many associated cancers the page DISPLAYS. The count (n_cancers) is over the whole
# scanned+filtered set; this is just the top slice shown, by score.
_TOP_CANCERS = 25


async def _gql(client: httpx.AsyncClient, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """POST a GraphQL query, surfacing the `errors` array (see enrich_cancer._gql)."""
    r = await client.post(ENDPOINT, json={"query": query, "variables": variables})
    body: dict[str, Any] | None = None
    try:
        body = r.json()
    except ValueError:
        body = None
    if body and body.get("errors"):
        raise RuntimeError("; ".join(e.get("message", "") for e in body["errors"]))
    r.raise_for_status()
    return (body or {}).get("data") or {}


@dataclass
class TargetEnrichStats:
    targets: int = 0
    enriched: int = 0
    facts_written: int = 0
    facts_source_failed: int = 0
    records_ok: int = 0
    records_failed: int = 0

    def report(self) -> str:
        return (
            f"targets={self.targets} enriched={self.enriched} "
            f"facts={self.facts_written} source_failed={self.facts_source_failed}"
        )


@dataclass
class ReverseResult:
    """The associated-cancers source's answer plus the two catalog-row fields it measures.

    approved_name and n_cancers are None when NOT measured (an outage, or a target Open
    Targets could not resolve) -- distinct from n_cancers == 0, which is a real measurement
    (resolved, none of its associated diseases are cancers we list). mark_enriched writes the
    catalog columns only when they are not None, so an outage never blanks the last good ones.
    """

    record: SourceRecord
    approved_name: str | None
    n_cancers: int | None


async def opentargets_associated_cancers(
    client: httpx.AsyncClient, target: Target, catalog_ids: set[str]
) -> ReverseResult:
    """The cancers (in our catalog) a target is associated with, from the OT reverse query."""
    source, key = "opentargets", "associated_cancers"
    url = f"https://platform.opentargets.org/target/{target.ensembl_id}"
    retrieved_at = utcnow()
    prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}
    try:
        data = await _gql(client, _REVERSE_QUERY, {"id": target.ensembl_id, "n": _SCAN_DISEASES})
    except Exception as exc:
        # An outage, recorded as a source_failed fact so the page reads "Open Targets
        # unavailable" -- never "no cancers". name/n_cancers stay unmeasured (None).
        return ReverseResult(
            SourceRecord(
                source,
                target.ensembl_id,
                ok=False,
                provenance=prov,
                facts={key: failed(source, str(exc), source_url=url)},
                error=str(exc),
                outage=True,
            ),
            approved_name=None,
            n_cancers=None,
        )

    t = data.get("target")
    if t is None:
        # Open Targets answered but does not resolve this Ensembl id (deprecated/remapped).
        # A lookup failure, NOT "no cancers": write no fact, so it never becomes a measured
        # EMPTY claiming this target drives nothing. Mirrors the disease-not-resolved branch.
        return ReverseResult(
            SourceRecord(
                source,
                target.ensembl_id,
                ok=False,
                provenance=prov,
                error="Open Targets did not resolve this target id",
            ),
            approved_name=None,
            n_cancers=None,
        )

    approved_name = t.get("approvedName")
    rows = (t.get("associatedDiseases") or {}).get("rows") or []
    # Sort defensively so "top by score" holds on the fetched set even if a future release
    # changes the within-page ordering.
    rows.sort(key=lambda r: r.get("score") or 0.0, reverse=True)
    cancers = [
        {
            "disease_id": (r.get("disease") or {}).get("id"),
            "name": (r.get("disease") or {}).get("name"),
            "score": round(r.get("score") or 0.0, 3),
        }
        for r in rows
        if (r.get("disease") or {}).get("id") in catalog_ids
    ]
    if len(rows) >= _SCAN_DISEASES:
        # The scan filled up: a catalog cancer scoring below the scanned page would be missed,
        # so n_cancers is a floor. Logged rather than silently undercounted.
        logger.warning(
            "associated_cancers scan saturated for %s: n_cancers=%d may undercount; "
            "raise _SCAN_DISEASES",
            target.ensembl_id,
            len(cancers),
        )

    if not cancers:
        # Resolved, but none of its associated diseases are cancers we list. A measured EMPTY
        # ("we looked, none in our catalog"), and n_cancers = 0 is that measurement.
        return ReverseResult(
            SourceRecord(
                source,
                target.ensembl_id,
                ok=True,
                facts={key: fact({}, source, source_url=url, retrieved_at=retrieved_at)},
                provenance=prov,
            ),
            approved_name=approved_name,
            n_cancers=0,
        )

    value = {"n_cancers": len(cancers), "cancers": cancers[:_TOP_CANCERS]}
    return ReverseResult(
        SourceRecord(
            source,
            target.ensembl_id,
            ok=True,
            facts={key: fact(value, source, source_url=url, retrieved_at=retrieved_at)},
            provenance=prov,
        ),
        approved_name=approved_name,
        n_cancers=len(cancers),
    )


async def _save_source_record(
    repo: TargetRepository, ensembl_id: str, record: SourceRecord, stats: TargetEnrichStats
) -> None:
    if record.error and not record.facts:
        # The source answered with no data and it is not an outage (Open Targets does not
        # resolve the id): nothing to record. Writing an empty fact would claim "no cancers"
        # for a target we could not look up.
        stats.records_failed += 1
        return
    await repo.save_record(ensembl_id, record)
    stats.facts_written += len(record.facts)
    failed_here = len(record.failed_facts)
    stats.facts_source_failed += failed_here
    if failed_here:
        stats.records_failed += 1
    else:
        stats.records_ok += 1


async def enrich_target(
    session: AsyncSession,
    target: Target,
    client: httpx.AsyncClient,
    catalog_ids: set[str],
    stats: TargetEnrichStats,
    *,
    commit_each: bool = False,
) -> None:
    """Fetch the associated-cancers source for one target and persist the result.

    last_enriched_at is stamped even when the source failed -- it records that we *looked*,
    distinct from a never-analyzed target. name and n_cancers are updated only when actually
    measured (see mark_enriched)."""
    repo = TargetRepository(session)
    result = await opentargets_associated_cancers(client, target, catalog_ids)
    await _save_source_record(repo, target.ensembl_id, result.record, stats)
    if commit_each:
        await session.commit()
    await repo.mark_enriched(
        target.ensembl_id, utcnow(), name=result.approved_name, n_cancers=result.n_cancers
    )
    stats.enriched += 1


async def enrich_target_catalog(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int | None = None,
    ensembl_id: str | None = None,
    only_unenriched: bool = False,
    stale_before: datetime | None = None,
) -> TargetEnrichStats:
    """Bulk-enrich targets (manual runs and the refresh cron). Mirrors enrich_cancer_catalog:
    last_enriched_at is both the never-touched marker and the freshness clock, so
    only_unenriched (fill) and stale_before (refresh) select over the one column."""
    if client is None:
        async with build_client() as owned:
            return await enrich_target_catalog(
                session,
                client=owned,
                limit=limit,
                ensembl_id=ensembl_id,
                only_unenriched=only_unenriched,
                stale_before=stale_before,
            )

    stats = TargetEnrichStats()
    repo = TargetRepository(session)
    # The catalog id set, loaded once and reused across the batch (see all_cancer_ids).
    catalog_ids = await CancerRepository(session).all_cancer_ids()

    targets = await repo.enrichment_targets(
        limit=limit,
        ensembl_id=ensembl_id,
        only_unenriched=only_unenriched,
        stale_before=stale_before,
    )
    stats.targets = len(targets)
    logger.info("enriching %d targets", len(targets))

    for target in targets:
        await enrich_target(session, target, client, catalog_ids, stats)
        await session.commit()

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", dest="ensembl_id", help="enrich one target by Ensembl id")
    parser.add_argument("--limit", type=int, help="max targets to enrich")
    parser.add_argument(
        "--only-missing", action="store_true", help="only targets never enriched yet"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        stats = await enrich_target_catalog(
            session,
            limit=args.limit,
            ensembl_id=args.ensembl_id,
            only_unenriched=args.only_missing,
        )

    print("\n=== target enrichment ===")
    print(f"  targets                : {stats.targets}")
    print(f"  enriched               : {stats.enriched}")
    print(f"  facts written          : {stats.facts_written}")
    print(f"  facts source-failed    : {stats.facts_source_failed}")


if __name__ == "__main__":
    asyncio.run(main())
