"""The target catalog: seed the third entity from the target landscapes we already hold.

Drives the real backfill against a real database. Pins the invariants that make the seed
honest: targets are deduped across cancers by Ensembl id, a landscape that failed or is empty
contributes nothing, a row missing a symbol is skipped (never a NULL-symbol catalog row),
and `name` / `n_cancers` are left NULL -- "not yet measured", not a measured zero -- for
enrich_target to fill. The idempotent upsert must never clobber those enriched fields on a
re-run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.backfill_target_catalog import backfill_target_catalog
from backend.ingestion.base import SourceRecord, fact, failed
from backend.models import Target
from backend.repositories.cancers import CancerRepository


def _landscape(*targets: tuple[str, str | None]) -> dict[str, Any]:
    """A target_landscape fact value in the shape opentargets_target_landscape stores:
    a threshold, a strong count, and the display rows (ensembl_id + symbol are what the
    backfill reads)."""
    rows: list[dict[str, Any]] = [
        {
            "symbol": symbol,
            "ensembl_id": ensembl_id,
            "score": 0.8,
            "evidence_types": [],
            "sm_tractable": True,
            "ab_tractable": False,
            "drug_status": "approved",
        }
        for ensembl_id, symbol in targets
    ]
    return {"threshold": 0.5, "n_strong": len(rows), "targets": rows}


async def _seed_cancer_landscape(
    cancers: CancerRepository, disease_id: str, name: str, landscape_fact: Any
) -> None:
    await cancers.upsert_cancer(disease_id, name=name, n_drugs=1, n_targets=5)
    await cancers.save_record(
        disease_id,
        SourceRecord(
            "opentargets",
            disease_id,
            ok=True,
            facts={"target_landscape": landscape_fact},
        ),
    )


async def _catalog(session: AsyncSession) -> dict[str, Target]:
    session.expire_all()  # force DB reads, not stale identity-map objects
    rows = (await session.execute(select(Target))).scalars().all()
    return {t.ensembl_id: t for t in rows}


@pytest.fixture
async def seeded(session: AsyncSession) -> None:
    """Four cancers: two OK landscapes that share EGFR (dedupe) and carry a null-symbol row
    (skip), one source_failed landscape and one empty landscape (both contribute nothing)."""
    cancers = CancerRepository(session)
    await _seed_cancer_landscape(
        cancers,
        "MONDO_0000001",
        "cancer one",
        fact(
            _landscape(("ENSG_EGFR", "EGFR"), ("ENSG_KRAS", "KRAS"), ("ENSG_NOSYM", None)),
            "opentargets",
        ),
    )
    await _seed_cancer_landscape(
        cancers,
        "MONDO_0000002",
        "cancer two",
        # EGFR again (must dedupe to one catalog row), plus a distinct target.
        fact(_landscape(("ENSG_EGFR", "EGFR"), ("ENSG_ALK", "ALK")), "opentargets"),
    )
    await _seed_cancer_landscape(
        cancers, "MONDO_0000003", "cancer three", failed("opentargets", "OT outage")
    )
    await _seed_cancer_landscape(
        cancers,
        "MONDO_0000004",
        "cancer four",
        fact({}, "opentargets"),  # EMPTY landscape
    )
    await session.commit()


async def test_backfill_seeds_deduped_targets_leaving_enrichment_fields_null(
    session: AsyncSession, seeded: None
) -> None:
    stats = await backfill_target_catalog(session)

    catalog = await _catalog(session)
    # EGFR (shared), KRAS, ALK -- three distinct. The null-symbol row is skipped, and the
    # failed + empty landscapes carry no targets, so nothing leaks from them.
    assert set(catalog) == {"ENSG_EGFR", "ENSG_KRAS", "ENSG_ALK"}
    assert stats.landscape_targets == 3
    assert stats.loaded == 3

    assert catalog["ENSG_EGFR"].symbol == "EGFR"
    assert catalog["ENSG_KRAS"].symbol == "KRAS"

    # The load-bearing honest-state: enrichment fields are NULL, not 0/"" -- "never measured",
    # distinct from a measured zero. A default of 0 here would be the None-vs-0 trap.
    for t in catalog.values():
        assert t.name is None
        assert t.n_cancers is None
        assert t.last_enriched_at is None


async def test_backfill_excludes_null_symbol_failed_and_empty(
    session: AsyncSession, seeded: None
) -> None:
    await backfill_target_catalog(session)
    catalog = await _catalog(session)
    # The null-symbol row never becomes a NULL-symbol catalog row (which would violate the
    # NOT NULL symbol column), and nothing leaks from the source_failed (MONDO_3) or empty
    # (MONDO_4) landscapes -- they carry no targets array at all.
    assert "ENSG_NOSYM" not in catalog
    assert set(catalog) == {"ENSG_EGFR", "ENSG_KRAS", "ENSG_ALK"}


async def test_backfill_only_missing_skips_existing(session: AsyncSession, seeded: None) -> None:
    await backfill_target_catalog(session)
    stats = await backfill_target_catalog(session, only_missing=True)
    assert stats.landscape_targets == 3
    assert stats.loaded == 0
    assert stats.skipped_existing == 3


async def test_upsert_does_not_clobber_enriched_fields(session: AsyncSession, seeded: None) -> None:
    await backfill_target_catalog(session)

    # Simulate enrich_target having filled the descriptive/measured fields -- via a plain
    # UPDATE, which is how Phase 2 will do it (mirroring cancer's mark_enriched: a partial
    # upsert cannot, because the NOT NULL `symbol` check rejects the candidate tuple before
    # ON CONFLICT can redirect to UPDATE).
    when = datetime(2026, 7, 19, tzinfo=UTC)
    await session.execute(
        update(Target)
        .where(Target.ensembl_id == "ENSG_EGFR")
        .values(name="epidermal growth factor receptor", n_cancers=7, last_enriched_at=when)
    )
    await session.commit()

    # Now an OT gene rename: both EGFR-bearing landscapes come back with a corrected symbol
    # (both, so the DISTINCT ON pick is unambiguous). A re-run of the backfill must do BOTH
    # halves of the upsert on conflict: WRITE the passed column (symbol refreshed in place --
    # this bites under a DO-NOTHING regression, where it would stay "EGFR"), and NOT touch the
    # columns it was not given (the enriched name / n_cancers / last_enriched_at survive).
    cancers = CancerRepository(session)
    await cancers.save_record(
        "MONDO_0000001",
        SourceRecord(
            "opentargets",
            "MONDO_0000001",
            ok=True,
            facts={
                "target_landscape": fact(
                    _landscape(("ENSG_EGFR", "EGFR2"), ("ENSG_KRAS", "KRAS")), "opentargets"
                )
            },
        ),
    )
    await cancers.save_record(
        "MONDO_0000002",
        SourceRecord(
            "opentargets",
            "MONDO_0000002",
            ok=True,
            facts={
                "target_landscape": fact(
                    _landscape(("ENSG_EGFR", "EGFR2"), ("ENSG_ALK", "ALK")), "opentargets"
                )
            },
        ),
    )
    await session.commit()

    await backfill_target_catalog(session)
    egfr = (await _catalog(session))["ENSG_EGFR"]
    assert egfr.symbol == "EGFR2"  # passed column IS written on conflict (refreshed in place)
    assert egfr.name == "epidermal growth factor receptor"  # un-passed columns survive
    assert egfr.n_cancers == 7
    assert egfr.last_enriched_at == when
