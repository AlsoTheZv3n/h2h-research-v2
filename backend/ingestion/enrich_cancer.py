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
from collections import defaultdict
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

# How many top associated targets the landscape card DISPLAYS: enough to show the
# established drivers plus a few less-obvious ones, not the ~12,000 Open Targets lists.
_TOP_TARGETS = 15

# How many to SCAN when counting strong associations. Open Targets returns associations
# sorted by score descending, so the strong ones (>= _STRONG_SCORE) are all within the
# first few hundred; 600 covers every cancer measured (the busiest, breast, has ~293
# above the threshold) with headroom.
_SCAN_TARGETS = 600

# The "strong association" cut, chosen from the real score distribution rather than a
# guess: Open Targets returns everything with ANY evidence (12,000-18,000 targets per
# cancer -- nearly the whole genome), which makes the raw total a threshold artifact, not
# a finding. At >= 0.5 (the midpoint of the 0-1 score) the count drops to the low hundreds
# -- NSCLC 117, breast 293 -- the targets with real, converging evidence. The number is
# never shown without this threshold beside it (the metric would mislead otherwise).
_STRONG_SCORE = 0.5

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

_PIPELINE_QUERY = """
query Pipeline($id: String!) {
  disease(efoId: $id) {
    id
    drugAndClinicalCandidates {
      count
      rows {
        maxClinicalStage
        drug {
          id
          name
          drugType
          mechanismsOfAction { rows { mechanismOfAction } }
        }
      }
    }
  }
}
"""

# Clinical stages in descending order, most advanced first -- how the pipeline card
# reads top to bottom. Open Targets' maxClinicalStage enum (verified live: APPROVAL,
# PHASE_4, PREAPPROVAL, PHASE_3, PHASE_2_3, PHASE_2, PHASE_1_2, PHASE_1, EARLY_PHASE_1,
# PHASE_0, PRECLINICAL all occur). PREAPPROVAL (submitted, awaiting approval) is a genuinely
# advanced stage and must rank near the top, not fall into the alphabetical tail -- so the
# enum is listed in full. Only a truly-unknown value sorts to the end.
_PHASE_ORDER = (
    "APPROVAL",
    "PHASE_4",
    "PREAPPROVAL",
    "PHASE_3",
    "PHASE_2_3",
    "PHASE_2",
    "PHASE_1_2",
    "PHASE_1",
    "EARLY_PHASE_1",
    "PHASE_0",
    "PRECLINICAL",
)
_STAGE_RANK = {stage: i for i, stage in enumerate(_PHASE_ORDER)}


def _stage_rank(stage: str) -> int:
    """Advancement rank -- lower is more advanced; unknown stages sort to the end."""
    return _STAGE_RANK.get(stage, len(_PHASE_ORDER))


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
            client, _TARGET_LANDSCAPE_QUERY, {"id": cancer.disease_id, "n": _SCAN_TARGETS}
        )
    except Exception as exc:
        # An outage (network, 5xx, 200-with-errors), recorded as a source_failed fact so
        # the card reads "Open Targets unavailable" -- never "no targets".
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            facts={key: failed(source, str(exc), source_url=url)},
            error=str(exc),
            outage=True,
        )

    disease = data.get("disease")
    if disease is None:
        # Open Targets answered but does not resolve this disease id (deprecated or
        # remapped across releases -- the same EFO->MONDO drift the catalog guards). That
        # is a lookup failure, NOT "this cancer has no targets": write no fact for the
        # key, mirroring the drug adapter's no-hit branch, so it never becomes a measured
        # EMPTY that claims zero druggable biology for a disease we could not look up.
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            error="Open Targets did not resolve this disease id",
        )

    rows = (disease.get("associatedTargets") or {}).get("rows") or []
    if not rows:
        # Resolved, but Open Targets lists no associated targets. A measured EMPTY ("we
        # looked, nothing there"), distinct from the not-found and outage cases above --
        # the same empty-dict branch the pipeline uses, so the status layer keeps saying
        # what it means rather than dressing an empty result as OK.
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=True,
            facts={key: fact({}, source, source_url=url, retrieved_at=retrieved_at)},
            provenance=prov,
        )
    # Open Targets returns associations score-descending, but sort defensively so the "top"
    # slice and the saturation check below hold on the fetched set even if a future release
    # changes the within-page ordering (the count itself still assumes OT returned the
    # top-scored page -- there is no client-side fix for that short of fetching everything).
    rows.sort(key=lambda r: r.get("score") or 0.0, reverse=True)
    # Count the strong associations across the whole scanned page (not just the 15
    # displayed): this is the headline metric, and it must be over the strong set, not
    # the ~12,000-with-any-evidence total that would read as "the whole genome". Require an
    # approvedSymbol -- the same basis the displayed list uses -- so the headline count and
    # the card can never contradict each other (a strong but un-symboled row would inflate
    # the number while the card, which needs a symbol to render a target, shows nothing).
    n_strong = sum(
        1
        for r in rows
        if (r.get("score") or 0.0) >= _STRONG_SCORE
        and (r.get("target") or {}).get("approvedSymbol")
    )
    if len(rows) >= _SCAN_TARGETS and (rows[-1].get("score") or 0.0) >= _STRONG_SCORE:
        # The scan filled up and even its weakest (last, since rows are score-descending)
        # row is still strong: the strong set may run past the scanned page, so n_strong is
        # a floor. Never observed -- breast, the busiest, is ~322 of a 600-row scan -- but
        # logged rather than silently undercounted if a future release ever crosses it.
        logger.warning(
            "target_landscape scan saturated for %s: n_strong>=%d may undercount; "
            "raise _SCAN_TARGETS",
            cancer.disease_id,
            n_strong,
        )
    display = [
        _target_row(r)
        for r in rows[:_TOP_TARGETS]
        if (r.get("target") or {}).get("approvedSymbol")
    ]
    # The value carries the threshold beside the count, so the number is never shown
    # without saying what it counts.
    value = {"threshold": _STRONG_SCORE, "n_strong": n_strong, "targets": display}
    return SourceRecord(
        source,
        cancer.disease_id,
        ok=True,
        facts={key: fact(value, source, source_url=url, retrieved_at=retrieved_at)},
        provenance=prov,
    )


def _group_pipeline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten the disease's drugs/candidates for the pipeline card.

    Deduped globally on the drug's ChEMBL id, keeping its most advanced stage (Open
    Targets can list a drug under several stages via different indications). Returns the
    flat drug list -- each with its stage, modality and mechanism -- for the table, plus a
    per-stage distribution (stage + true count) for the summary bars. No cap: the table
    pages client-side, so the whole pipeline is stored.
    """
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        drug = row.get("drug") or {}
        cid = drug.get("id")
        if not cid:
            continue
        stage = row.get("maxClinicalStage") or "UNKNOWN"
        prior = best.get(cid)
        if prior is not None and _stage_rank(prior["stage"]) <= _stage_rank(stage):
            continue  # already seen at an equal-or-more-advanced stage
        moas = [
            m["mechanismOfAction"]
            # `.get("rows") or []`, not `.get("rows", [])`: Open Targets returns rows as
            # JSON null (not absent), and the default only fires on an absent key -- so
            # the [] default would leave None and `for m in None` would crash out of the
            # source uncaught, writing no source_failed fact. Same guard as line 204.
            for m in (drug.get("mechanismsOfAction") or {}).get("rows") or []
            if m.get("mechanismOfAction")
        ]
        best[cid] = {
            "chembl_id": cid,
            "name": drug.get("name") or cid,
            "stage": stage,
            # Missing modality/mechanism stay null -> the UI renders an honest "—", never
            # a guessed value.
            "modality": drug.get("drugType"),
            "mechanism": moas[0] if moas else None,
        }

    if not best:
        return {}

    drugs = sorted(best.values(), key=lambda d: (_stage_rank(d["stage"]), d["name"] or ""))
    counts: dict[str, int] = defaultdict(int)
    for d in drugs:
        counts[d["stage"]] += 1
    order = [*_PHASE_ORDER, *sorted(s for s in counts if s not in _PHASE_ORDER)]
    by_phase = [{"stage": stage, "count": counts[stage]} for stage in order if stage in counts]
    return {"total": len(drugs), "by_phase": by_phase, "drugs": drugs}


async def opentargets_pipeline(client: httpx.AsyncClient, cancer: Cancer) -> SourceRecord:
    """The drugs and clinical candidates for this cancer, grouped by clinical stage.

    Open Targets' disease->drugs list already rolls the disease ontology up, so a drug
    indicated for a subtype (osimertinib for lung adenocarcinoma) is counted for the
    parent (NSCLC) -- which an exact disease-id match over stored drug indications would
    miss. The join is on the disease ID and the drilldown is on the ChEMBL ID; no name
    matching anywhere (the weave's hard rule).
    """
    source, key = "opentargets", "pipeline"
    url = f"https://platform.opentargets.org/disease/{cancer.disease_id}"
    retrieved_at = utcnow()
    prov: dict[str, Any] = {"source_url": url, "retrieved_at": retrieved_at}
    try:
        data = await _gql(client, _PIPELINE_QUERY, {"id": cancer.disease_id})
    except Exception as exc:
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            facts={key: failed(source, str(exc), source_url=url)},
            error=str(exc),
            outage=True,
        )
    disease = data.get("disease")
    if disease is None:
        return SourceRecord(
            source,
            cancer.disease_id,
            ok=False,
            provenance=prov,
            error="Open Targets did not resolve this disease id",
        )
    rows = (disease.get("drugAndClinicalCandidates") or {}).get("rows") or []
    pipeline = _group_pipeline(rows)
    # fact() classifies an empty dict as EMPTY -- "resolved, no drug programmes" --
    # distinct from the not-found and outage cases above.
    return SourceRecord(
        source,
        cancer.disease_id,
        ok=True,
        facts={key: fact(pipeline, source, source_url=url, retrieved_at=retrieved_at)},
        provenance=prov,
    )


def build_cancer_sources() -> list[CancerSource]:
    """The cancer evidence sources, assembled. Trial reality joins here next."""
    return [opentargets_target_landscape, opentargets_pipeline]


async def _save_source_record(
    repo: CancerRepository, disease_id: str, record: SourceRecord, stats: CancerEnrichStats
) -> None:
    if record.error and not record.facts:
        # The source answered with no data for this entity and it is not an outage (e.g.
        # Open Targets does not resolve the disease id): nothing to record. Writing an
        # empty fact would claim "no targets" for a disease we could not look up -- the
        # same lie the outage path is guarded against, pointed the other way.
        stats.records_failed += 1
        return
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
