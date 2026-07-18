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
from datetime import datetime

import httpx
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db import get_sessionmaker
from backend.ingestion.base import FactStatus, SourceAdapter, SourceRecord, failed, utcnow
from backend.ingestion.chembl import ChEMBLAdapter
from backend.ingestion.clinicaltrials import ClinicalTrialsAdapter
from backend.ingestion.http import build_client
from backend.ingestion.literature import LiteratureFetcher
from backend.ingestion.opentargets import OpenTargetsAdapter
from backend.ingestion.pubmed import PubMedAdapter
from backend.models import DataMaturity, Drug
from backend.repositories.drugs import DrugRepository, classify_maturity
from backend.repositories.literature import LiteratureRepository

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
    abstracts_embedded: int = 0
    drugs_with_a_failure: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"  drugs processed        : {self.drugs}",
            f"  source records ok      : {self.records_ok}",
            f"  source records failed  : {self.records_failed}",
            f"  facts written          : {self.facts_written}",
            f"  facts marked failed    : {self.facts_source_failed}",
            f"  abstracts embedded     : {self.abstracts_embedded}",
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
    settings = get_settings()
    return [
        ChEMBLAdapter(client),
        ClinicalTrialsAdapter(client),
        OpenTargetsAdapter(client),
        PubMedAdapter(
            client,
            api_key=settings.ncbi_api_key,
            tool=settings.ncbi_tool,
            email=settings.ncbi_email,
        ),
    ]


def build_literature_fetcher(client: httpx.AsyncClient) -> LiteratureFetcher:
    """The abstract fetcher for RAG, built like the adapters and from the same client.

    Separate from build_adapters because it produces documents, not facts: a
    LiteratureRecord saved via LiteratureRepository, not a SourceRecord of facts. But
    it is fetched in the same enrich job (see enrich_drug), because it IS a source in
    this pipeline -- and until it was, no production path fetched an abstract and the
    RAG chat was inert on every real drug.
    """
    settings = get_settings()
    return LiteratureFetcher(
        client,
        api_key=settings.ncbi_api_key,
        tool=settings.ncbi_tool,
        email=settings.ncbi_email,
    )


def _query_for(drug: Drug) -> str:
    """What to ask the sources about this drug.

    pref_name where we have it: ClinicalTrials.gov, Open Targets and PubMed have no
    idea what a ChEMBL id is.
    """
    return drug.pref_name or drug.chembl_id


async def _enrich_literature(
    session: AsyncSession, drug: Drug, query: str, fetcher: LiteratureFetcher, stats: EnrichStats
) -> None:
    """Fetch this drug's abstracts and persist them embedded, as part of enrichment.

    This is the link that was missing. LiteratureRepository.save embeds at save time
    (persist-without-embed leaves abstracts that can never be retrieved -- the hidden
    other end of the same bug), and stamps literature_fetched_at, so the retriever can
    tell "searched, nothing found" from "never searched".

    A failed fetch writes nothing and leaves the drug unsearched, which is correct: an
    index retries rather than recording an outage. The drug's *facts* (the PubMed hit
    count) are where a PubMed outage lands on the record.
    """
    record = await fetcher.fetch(query)
    embedded = await LiteratureRepository(session).save(drug.chembl_id, record)
    stats.abstracts_embedded += embedded
    if not record.ok:
        logger.info("%s: literature fetch failed: %s", drug.chembl_id, record.error)


async def _save_source_record(
    repo: DrugRepository,
    drug: Drug,
    adapter: SourceAdapter,
    record: SourceRecord,
    stats: EnrichStats,
) -> bool:
    """Persist one source's answer. Returns whether it contributed a failure."""
    if record.error and not record.facts:
        stats.records_failed += 1
        logger.info("%s: %s could not resolve: %s", drug.chembl_id, record.source, record.error)

        if record.outage:
            # An outage has to be written down. Storing nothing leaves the brief with no
            # rows from this source, so `unavailable` comes back empty and the API states
            # -- positively -- that nothing failed, while the UI says "Not collected" for
            # a mechanism ChEMBL simply could not be asked about. That is this project's
            # founding lie, arriving through the one path built to prevent it.
            #
            # A non-outage error means the source answered and does not know this drug.
            # Nothing to record: it has no opinion, and inventing source_failed rows
            # would be the same lie mirrored.
            await repo.save_record(
                drug.chembl_id,
                SourceRecord(
                    record.source,
                    record.query,
                    ok=False,
                    provenance=record.provenance,
                    facts={
                        key: failed(
                            record.source,
                            record.error,
                            source_url=record.provenance.get("source_url"),
                        )
                        for key in adapter.owned_keys
                    },
                ),
            )
            stats.facts_source_failed += len(adapter.owned_keys)
        return True

    stats.records_ok += 1
    await repo.save_record(drug.chembl_id, record)
    stats.facts_written += len(record.facts)
    failed_here = len(record.failed_facts)
    stats.facts_source_failed += failed_here
    return bool(failed_here)


async def enrich_drug(
    session: AsyncSession,
    drug: Drug,
    adapters: list[SourceAdapter],
    stats: EnrichStats,
    literature: LiteratureFetcher | None = None,
    *,
    commit_each: bool = False,
) -> None:
    """Fetch every source for one drug and persist the result.

    `literature` is a separate parameter rather than another entry in `adapters`
    because it returns documents, not facts, and takes a different save path. Optional
    so a test can enrich facts alone -- but the production call sites (enrich_catalog,
    the lazy brief) always pass it, and the full-loop acceptance test goes through one
    of those, because a test that omits it proves nothing about whether production
    wired it.

    `commit_each` persists each source as it returns rather than all at the end, so a
    reader polling a cold brief watches it fill card by card instead of staring at
    "analyzing" until the slowest source comes back. The interactive path turns it on;
    the bulk loader leaves it off and commits per wave. last_enriched_at is still set
    only at the end (in _promote), so the brief stays "enriching" -- not "ready" --
    until every source has been given its chance.
    """
    repo = DrugRepository(session)
    query = _query_for(drug)

    async def fetch(adapter: SourceAdapter) -> tuple[SourceAdapter, SourceRecord]:
        return adapter, await adapter.fetch(query)

    # as_completed, not gather: process each source the moment it returns, so commit_each
    # can make it visible without waiting on the others. Order does not matter -- _promote
    # keys the records by source.
    records: list[SourceRecord] = []
    had_failure = False
    for coro in asyncio.as_completed([fetch(a) for a in adapters]):
        adapter, record = await coro
        records.append(record)
        if await _save_source_record(repo, drug, adapter, record, stats):
            had_failure = True
        if commit_each:
            await session.commit()

    if had_failure:
        stats.drugs_with_a_failure.append(drug.chembl_id)

    # Literature is fetched here, in the same job, for the same reason the four fact
    # adapters are: it is a source this drug's brief needs. Skipping it is what made
    # the RAG chat inert in production.
    if literature is not None:
        await _enrich_literature(session, drug, query, literature, stats)

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
            # target_class moves in LOCKSTEP with primary_target, or the two diverge: on
            # re-enrichment a new primary target with no class would leave the previous
            # target's class stranded beside it (a transporter filed under "Kinase"). So
            # promote the class whenever the target changes -- an EMPTY class (Open
            # Targets answered, this target has no family) clears the column to NULL
            # ("Unclassified"). Only a SOURCE_FAILED class is left untouched, so an
            # outage never erases a class we already had.
            target_class = ot.facts.get("target_class")
            if target_class is not None and target_class.status is not FactStatus.SOURCE_FAILED:
                columns["target_class"] = target_class.value
        indications = ot.facts.get("indications")
        if indications is not None and indications.status is FactStatus.OK and indications.value:
            columns["primary_indication"] = indications.value[0]
        # Sync the drug->target relation the cancer landscape's catalog-link reads. Gated on
        # not-source_failed exactly like target_class above: an OT outage must never wipe the
        # drug's targets, but an EMPTY (measured "no targets annotated") legitimately clears
        # them. Keyed on Ensembl id -- never the symbol.
        target_ids = ot.facts.get("target_ids")
        if target_ids is not None and target_ids.status is not FactStatus.SOURCE_FAILED:
            await repo.sync_drug_targets(drug.chembl_id, target_ids.value or [])

    # maturity, now with a real answer for has_potency rather than a placeholder.
    resolved_type = columns.get("drug_type") or drug.drug_type
    smiles = None
    if chembl is not None:
        smiles_fact = chembl.facts.get("smiles")
        if smiles_fact is not None and smiles_fact.status is FactStatus.OK:
            smiles = smiles_fact.value
    smiles = smiles or drug.smiles

    # has_potency falls back to what we already knew, exactly as smiles and drug_type
    # do above -- it was the one field left out of the pattern. Defaulting it to False
    # meant a ChEMBL outage silently rewrote maturity FULL -> PARTIAL, publishing "some
    # cards will be empty" as a claim about the molecule when it was a fact about our
    # afternoon. Worse, the prior potency fact survives, so the brief showed a median
    # while the pill said the cards were empty.
    #
    # The predicate is `is not SOURCE_FAILED`, not `is OK`: an EMPTY summary is a
    # measured "no potency" and should legitimately drop to PARTIAL.
    summary = chembl.facts.get("ic50_summary") if chembl is not None else None
    if summary is not None and summary.status is not FactStatus.SOURCE_FAILED:
        has_potency = bool(summary.value and summary.value.get("n_exact"))
    else:
        has_potency = drug.maturity is DataMaturity.FULL

    columns["maturity"] = classify_maturity(
        resolved_type if isinstance(resolved_type, str) else None, smiles, has_potency
    )
    # Stamped even when every source failed: it records that we *looked*, which is a
    # different statement from "there is nothing here". A drug whose enrichment found
    # only outages has a brief full of source_failed facts -- an answer. A drug that
    # was never asked has no facts at all, and must not be mistaken for the first.
    columns["last_enriched_at"] = utcnow()
    await repo.upsert_drug(drug.chembl_id, **columns)


async def enrich_catalog(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int | None = None,
    chembl_id: str | None = None,
    only_unenriched: bool = False,
    stale_before: datetime | None = None,
) -> EnrichStats:
    if client is None:
        async with build_client() as owned:
            return await enrich_catalog(
                session,
                client=owned,
                limit=limit,
                chembl_id=chembl_id,
                only_unenriched=only_unenriched,
                stale_before=stale_before,
            )

    stats = EnrichStats()
    adapters = build_adapters(client)
    literature = build_literature_fetcher(client)

    query = select(Drug).order_by(Drug.max_phase.desc().nullslast(), Drug.chembl_id)
    if chembl_id:
        query = select(Drug).where(Drug.chembl_id == chembl_id)
    else:
        # The refresh pass's dedup and resumability, in one clause -- last_enriched_at
        # is both the "never touched" marker and the freshness clock, so no separate
        # bookkeeping. only_unenriched picks the never-touched drugs (fill); stale_before
        # picks the ones last looked at before the cutoff (refresh). Together they are
        # the fill-and-refresh selection; either alone is one half. A collision with an
        # on-demand enrich of the same drug is harmless -- enrich_drug upserts, so the
        # worst case is one drug fetched twice.
        conds: list[ColumnElement[bool]] = []
        if only_unenriched:
            conds.append(Drug.last_enriched_at.is_(None))
        if stale_before is not None:
            conds.append(Drug.last_enriched_at < stale_before)
        if conds:
            query = query.where(or_(*conds))
        if limit:
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
            await enrich_drug(session, drug, adapters, stats, literature)
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
