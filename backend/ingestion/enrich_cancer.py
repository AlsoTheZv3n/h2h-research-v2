"""On-demand enrichment of a cancer's evidence brief.

The disease-side twin of enrich.py, and the same reason for it: the catalog holds index
columns only, and a cancer's real evidence -- its target landscape today, its pipeline
and trial reality as later increments land -- is fetched the first time someone opens it
and served from Postgres after.

Each source is a self-contained async function returning a SourceRecord, so adding the
next block is adding a function to build_cancer_sources(), not touching the loop.
`commit_each` persists each source as it returns, so a polling page fills card by card.

Run:  uv run python -m backend.ingestion.enrich_cancer --disease MONDO_0005233
      uv run python -m backend.ingestion.enrich_cancer --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_sessionmaker
from backend.ingestion.base import SourceRecord, fact, failed, utcnow
from backend.ingestion.http import build_client
from backend.models import Cancer
from backend.repositories.cancers import CancerRepository

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"

# How many top associated targets the landscape card carries: enough to show the
# established drivers plus a few less-obvious ones, not the ~12,000 Open Targets lists.
_TOP_TARGETS = 15

_TARGET_LANDSCAPE_QUERY = """
query TargetLandscape($id: String!, $n: Int!) {
  disease(efoId: $id) {
    id
    associatedTargets(page: {index: 0, size: $n}) {
      count
      rows {
        score
        datatypeScores { id score }
        target { approvedSymbol tractability { label modality value } }
      }
    }
  }
}
"""

# A source: one function, one SourceRecord for one cancer.
CancerSource = Callable[[httpx.AsyncClient, Cancer], Awaitable[SourceRecord]]

_CONCURRENCY = 3


@dataclass
class CancerEnrichStats:
    cancers: int = 0
    enriched: int = 0
    records_ok: int = 0
    records_failed: int = 0
    facts_written: int = 0
    facts_source_failed: int = 0

    def report(self) -> str:
        return "\n".join(
            [
                f"  cancers enriched      : {self.enriched}",
                f"  source records ok     : {self.records_ok}",
                f"  source records failed : {self.records_failed}",
                f"  facts written         : {self.facts_written}",
                f"  facts marked failed   : {self.facts_source_failed}",
            ]
        )


async def _gql(client: httpx.AsyncClient, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """POST a GraphQL query, surfacing the `errors` array (see the OT adapter's _gql)."""
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


def _target_row(row: dict[str, Any]) -> dict[str, Any]:
    """One associated target, reduced to what the landscape card shows."""
    target = row.get("target") or {}
    tractability = target.get("tractability") or []
    return {
        "symbol": target.get("approvedSymbol"),
        "score": round(row.get("score") or 0.0, 3),
        # The typed evidence channels behind the association ("clinical",
        # "somatic_mutation", ...), so a reader sees whether it rests on trials or on
        # literature alone.
        "evidence_types": [e["id"] for e in (row.get("datatypeScores") or []) if e.get("id")],
        # The drugged/undrugged story starts here: is there a tractable modality at all?
        "sm_tractable": any(t.get("modality") == "SM" and t.get("value") for t in tractability),
        "ab_tractable": any(t.get("modality") == "AB" and t.get("value") for t in tractability),
    }


async def opentargets_target_landscape(client: httpx.AsyncClient, cancer: Cancer) -> SourceRecord:
    """The disease's top associated targets, with score, evidence channels and tractability."""
    source, key = "opentargets", "target_landscape"
    url = f"https://platform.opentargets.org/disease/{cancer.disease_id}"
    retrieved_at = utcnow()
    prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}
    try:
        data = await _gql(
            client, _TARGET_LANDSCAPE_QUERY, {"id": cancer.disease_id, "n": _TOP_TARGETS}
        )
        rows = ((data.get("disease") or {}).get("associatedTargets") or {}).get("rows") or []
    except Exception as exc:
        # An outage, recorded as a source_failed fact so the card reads "Open Targets
        # unavailable" -- never "no targets", which would be a claim about the disease.
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            facts={key: failed(source, str(exc), source_url=url)},
            error=str(exc),
            outage=True,
        )
    landscape = [_target_row(r) for r in rows if (r.get("target") or {}).get("approvedSymbol")]
    # fact() classifies an empty list as EMPTY -- "Open Targets answered, no associated
    # targets" -- a real measured negative, distinct from the source_failed above.
    return SourceRecord(
        source,
        cancer.disease_id,
        ok=True,
        facts={key: fact(landscape, source, source_url=url, retrieved_at=retrieved_at)},
        provenance=prov,
    )


def build_cancer_sources() -> list[CancerSource]:
    """The cancer evidence sources, assembled. Pipeline and trial reality join here."""
    return [opentargets_target_landscape]


async def _save_source_record(
    repo: CancerRepository, disease_id: str, record: SourceRecord, stats: CancerEnrichStats
) -> None:
    await repo.save_record(disease_id, record)
    stats.facts_written += len(record.facts)
    failed_here = len(record.failed_facts)
    stats.facts_source_failed += failed_here
    if failed_here:
        stats.records_failed += 1
    else:
        stats.records_ok += 1


async def enrich_cancer(
    session: AsyncSession,
    cancer: Cancer,
    client: httpx.AsyncClient,
    sources: list[CancerSource],
    stats: CancerEnrichStats,
    *,
    commit_each: bool = False,
) -> None:
    """Fetch every source for one cancer and persist the result.

    `commit_each` persists each source as it returns, so a polling page fills card by
    card. last_enriched_at is set at the end, so the brief stays "enriching" -- not
    "ready" -- until every source has had its chance.
    """
    repo = CancerRepository(session)
    for source_fn in sources:
        record = await source_fn(client, cancer)
        await _save_source_record(repo, cancer.disease_id, record, stats)
        if commit_each:
            await session.commit()

    # Stamped even when every source failed: it records that we *looked*, which a brief
    # full of source_failed facts is -- distinct from a never-analyzed cancer with no
    # facts at all. The same last_enriched_at semantics the drug side carries. A plain
    # UPDATE (mark_enriched), not an upsert -- see the method for why NOT NULL forces it.
    await repo.mark_enriched(cancer.disease_id, utcnow())
    stats.enriched += 1


async def enrich_cancer_catalog(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int | None = None,
    disease_id: str | None = None,
    only_unenriched: bool = False,
    stale_before: datetime | None = None,
) -> CancerEnrichStats:
    """Bulk-enrich cancers (manual runs and, later, the refresh cron).

    last_enriched_at is both the never-touched marker and the freshness clock, so
    only_unenriched (fill) and stale_before (refresh) select over the one column, like
    enrich_catalog.
    """
    if client is None:
        async with build_client() as owned:
            return await enrich_cancer_catalog(
                session,
                client=owned,
                limit=limit,
                disease_id=disease_id,
                only_unenriched=only_unenriched,
                stale_before=stale_before,
            )

    stats = CancerEnrichStats()
    sources = build_cancer_sources()

    query = select(Cancer).order_by(Cancer.n_drugs.desc(), Cancer.disease_id)
    if disease_id:
        query = select(Cancer).where(Cancer.disease_id == disease_id)
    else:
        conds: list[ColumnElement[bool]] = []
        if only_unenriched:
            conds.append(Cancer.last_enriched_at.is_(None))
        if stale_before is not None:
            conds.append(Cancer.last_enriched_at < stale_before)
        if conds:
            query = query.where(or_(*conds))
        if limit:
            query = query.limit(limit)

    cancers = list((await session.execute(query)).scalars().all())
    stats.cancers = len(cancers)
    logger.info("enriching %d cancers", len(cancers))

    for i in range(0, len(cancers), _CONCURRENCY):
        wave = cancers[i : i + _CONCURRENCY]
        for cancer in wave:
            await enrich_cancer(session, cancer, client, sources, stats)
        await session.commit()
        logger.info("committed: %d/%d cancers enriched", stats.enriched, len(cancers))

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich cancers with their evidence blocks.")
    parser.add_argument("--limit", type=int, help="only the first N cancers (most-drugged first)")
    parser.add_argument(
        "--disease", dest="disease_id", help="a single disease id, e.g. MONDO_0005233"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        stats = await enrich_cancer_catalog(session, limit=args.limit, disease_id=args.disease_id)

    print("\n=== cancer enrichment ===")
    print(stats.report())


if __name__ == "__main__":
    asyncio.run(main())
