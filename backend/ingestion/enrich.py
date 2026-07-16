"""Run every source adapter over the catalog and persist what they return.

This is the step that makes the fact table real. Without it the catalog holds index
columns only, `GET /drugs/{id}` answers `facts: {}, unavailable: []` for every drug
-- which positively asserts "no source failed, nothing to report" -- and the four
adapters are code that only the test suite ever executes.

Same contract as the catalog loader, for the same reason (ChEMBL):
  idempotent  facts upsert on (drug, key, source); re-running refreshes in place
  resumable   one drug's failure never touches another's; commits land per drug

Run:  uv run python -m backend.ingestion.enrich                 # whole catalog
      uv run python -m backend.ingestion.enrich --limit 20      # a taste
      uv run python -m backend.ingestion.enrich --drug CHEMBL4594350
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db import get_sessionmaker
from backend.ingestion.base import FactStatus, SourceAdapter, SourceRecord
from backend.ingestion.chembl import ChEMBLAdapter
from backend.ingestion.clinicaltrials import ClinicalTrialsAdapter
from backend.ingestion.http import build_client
from backend.ingestion.opentargets import OpenTargetsAdapter
from backend.ingestion.pubmed import PubMedAdapter
from backend.models import Drug
from backend.repositories.drugs import DrugRepository, classify_maturity

logger = logging.getLogger(__name__)

# Modest: four adapters already fire per drug, so this is 4x the number below.
_CONCURRENCY = 3


@dataclass
class EnrichStats:
    drugs: int = 0
    enriched: int = 0
    records_ok: int = 0
    records_failed: int = 0
    facts_written: int = 0
    facts_source_failed: int = 0
    drugs_with_a_failure: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"  drugs processed        : {self.drugs}",
            f"  source records ok      : {self.records_ok}",
            f"  source records failed  : {self.records_failed}",
            f"  facts written          : {self.facts_written}",
            f"  facts marked failed    : {self.facts_source_failed}",
        ]
        if self.drugs_with_a_failure:
            lines.append(
                f"  !! drugs with at least one source failure: {len(self.drugs_with_a_failure)}"
            )
            lines.append(f"     first few: {self.drugs_with_a_failure[:5]}")
            # The counts above are a floor, not a finding about the data -- the same
            # rule the spike's coverage table had to learn.
            lines.append("  NOTE: re-run to refresh those; their facts say which source failed.")
        return "\n".join(lines)


def build_adapters(client: httpx.AsyncClient) -> list[SourceAdapter]:
    """The plugin layer, assembled. One adapter per source, one shared client."""
    return [
        ChEMBLAdapter(client),
        ClinicalTrialsAdapter(client),
        OpenTargetsAdapter(client),
        PubMedAdapter(client, api_key=get_settings().ncbi_api_key),
    ]


def _query_for(drug: Drug) -> str:
    """What to ask the sources about this drug.

    pref_name where we have it: ClinicalTrials.gov, Open Targets and PubMed have no
    idea what a ChEMBL id is.
    """
    return drug.pref_name or drug.chembl_id


async def enrich_drug(
    session: AsyncSession, drug: Drug, adapters: list[SourceAdapter], stats: EnrichStats
) -> None:
    """Fetch every source for one drug and persist the result."""
    repo = DrugRepository(session)
    query = _query_for(drug)

    records: list[SourceRecord] = await asyncio.gather(*(a.fetch(query) for a in adapters))

    had_failure = False
    for record in records:
        if record.error and not record.facts:
            # Hard failure: the source could not resolve the entity, so there is
            # nothing to store. Counted, and visible in the run's report.
            stats.records_failed += 1
            had_failure = True
            logger.info("%s: %s could not resolve: %s", drug.chembl_id, record.source, record.error)
            continue

        stats.records_ok += 1
        await repo.save_record(drug.chembl_id, record)
        stats.facts_written += len(record.facts)
        failed_here = len(record.failed_facts)
        stats.facts_source_failed += failed_here
        had_failure = had_failure or bool(failed_here)

    if had_failure:
        stats.drugs_with_a_failure.append(drug.chembl_id)

    await _promote(session, repo, drug, records)
    stats.enriched += 1


async def _promote(
    session: AsyncSession, repo: DrugRepository, drug: Drug, records: list[SourceRecord]
) -> None:
    """Lift the facts the overview reads into the catalog row."""
    by_source = {r.source: r for r in records}

    chembl = by_source.get("chembl")
    if chembl is not None and chembl.facts:
        await repo.promote_index_columns(drug.chembl_id, chembl)

    columns: dict[str, object] = {}

    # Open Targets owns modality and target annotation -- ChEMBL's molecule_type is
    # coarser ("Antibody" vs "Antibody drug conjugate").
    ot = by_source.get("opentargets")
    if ot is not None:
        drug_type = ot.facts.get("drug_type")
        if drug_type is not None and drug_type.status is FactStatus.OK:
            columns["drug_type"] = drug_type.value
        targets = ot.facts.get("targets")
        if targets is not None and targets.status is FactStatus.OK and targets.value:
            columns["primary_target"] = targets.value[0]
        indications = ot.facts.get("indications")
        if indications is not None and indications.status is FactStatus.OK and indications.value:
            columns["primary_indication"] = indications.value[0]

    # maturity, now with a real answer for has_potency rather than a placeholder.
    resolved_type = columns.get("drug_type") or drug.drug_type
    smiles = None
    has_potency = False
    if chembl is not None:
        smiles_fact = chembl.facts.get("smiles")
        if smiles_fact is not None and smiles_fact.status is FactStatus.OK:
            smiles = smiles_fact.value
        summary = chembl.facts.get("ic50_summary")
        if summary is not None and summary.status is FactStatus.OK and summary.value:
            has_potency = bool(summary.value.get("n_exact"))
    smiles = smiles or drug.smiles

    columns["maturity"] = classify_maturity(
        resolved_type if isinstance(resolved_type, str) else None, smiles, has_potency
    )
    await repo.upsert_drug(drug.chembl_id, **columns)


async def enrich_catalog(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int | None = None,
    chembl_id: str | None = None,
) -> EnrichStats:
    if client is None:
        async with build_client() as owned:
            return await enrich_catalog(session, client=owned, limit=limit, chembl_id=chembl_id)

    stats = EnrichStats()
    adapters = build_adapters(client)

    query = select(Drug).order_by(Drug.max_phase.desc().nullslast(), Drug.chembl_id)
    if chembl_id:
        query = select(Drug).where(Drug.chembl_id == chembl_id)
    elif limit:
        query = query.limit(limit)

    drugs = list((await session.execute(query)).scalars().all())
    stats.drugs = len(drugs)
    logger.info("enriching %d drugs", len(drugs))

    for i in range(0, len(drugs), _CONCURRENCY):
        wave = drugs[i : i + _CONCURRENCY]
        # Sequential within the wave: one AsyncSession is not safe to share across
        # concurrent writers. The fetches are what is slow, and those are batched by
        # asyncio.gather inside enrich_drug.
        for drug in wave:
            await enrich_drug(session, drug, adapters, stats)
        # Commit per wave: a run over thousands of drugs must not be all-or-nothing.
        await session.commit()
        logger.info("committed: %d/%d drugs enriched", stats.enriched, len(drugs))

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run every source adapter over the catalog.")
    parser.add_argument("--limit", type=int, help="only the first N drugs (highest phase first)")
    parser.add_argument("--drug", dest="chembl_id", help="a single ChEMBL id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with get_sessionmaker()() as session:
        stats = await enrich_catalog(session, limit=args.limit, chembl_id=args.chembl_id)

    print("\n=== enrichment ===")
    print(stats.report())


if __name__ == "__main__":
    asyncio.run(main())
