"""The refresh cron's selection: fill the never-touched, re-enrich the stale, leave
the fresh alone.

This replaced the pre-warmer. The whole of the change is one query clause -- last
looked at NULL (fill) OR before the cutoff (refresh) -- so that clause is what the
tests pin: a fresh drug must not be re-fetched every pass (that would be the tight loop
the cron exists to stop), and a stale one must not be skipped forever.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import utcnow
from backend.ingestion.enrich import enrich_catalog
from backend.models import Drug
from backend.repositories import DrugRepository

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
CT = "https://clinicaltrials.gov/api/v2/studies"
OT = "https://api.platform.opentargets.org/api/v4/graphql"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _mock_sources_down() -> None:
    """Every source 500s. Enrichment still stamps last_enriched_at (a failed look is a
    look), so the pass's *selection* is what these tests observe -- not the fetch, which
    other suites cover against real payloads."""
    for url in (
        f"{CHEMBL}/molecule/search.json",
        f"{CT}",
        f"{EUTILS}/esearch.fcgi",
    ):
        respx.get(url__startswith=url).mock(return_value=httpx.Response(500))
    respx.post(OT).mock(return_value=httpx.Response(500))


@pytest.fixture
async def three_ages(session: AsyncSession) -> dict[str, object]:
    """One drug never enriched, one stale, one fresh."""
    repo = DrugRepository(session)
    now = utcnow()
    stale_ts = now - timedelta(days=60)
    fresh_ts = now - timedelta(days=1)
    await repo.upsert_drug("CHEMBL_NULL", pref_name="nullmab", max_phase=2)
    await repo.upsert_drug(
        "CHEMBL_STALE", pref_name="stalinib", max_phase=2, last_enriched_at=stale_ts
    )
    await repo.upsert_drug(
        "CHEMBL_FRESH", pref_name="freshinib", max_phase=2, last_enriched_at=fresh_ts
    )
    await session.commit()
    return {"fresh_ts": fresh_ts}


@respx.mock
async def test_fill_and_refresh_selects_null_and_stale_but_not_fresh(
    session: AsyncSession, fast_client: httpx.AsyncClient, three_ages: dict[str, object]
) -> None:
    _mock_sources_down()
    cutoff = utcnow() - timedelta(days=30)

    stats = await enrich_catalog(
        session, client=fast_client, only_unenriched=True, stale_before=cutoff
    )

    # Two selected: the never-touched and the stale. The fresh one is left alone.
    assert stats.drugs == 2

    fresh = await session.get(Drug, "CHEMBL_FRESH")
    assert fresh is not None
    await session.refresh(fresh)
    assert fresh.last_enriched_at == three_ages["fresh_ts"], (
        "a fresh drug was needlessly re-fetched"
    )

    # The stale one was re-enriched: its clock moved past the cutoff.
    stale = await session.get(Drug, "CHEMBL_STALE")
    assert stale is not None
    await session.refresh(stale)
    assert stale.last_enriched_at is not None and stale.last_enriched_at > cutoff

    # The never-touched one is now enriched (stamped even though every source was down).
    nulled = await session.get(Drug, "CHEMBL_NULL")
    assert nulled is not None
    await session.refresh(nulled)
    assert nulled.last_enriched_at is not None


@respx.mock
async def test_fill_only_still_skips_everything_already_enriched(
    session: AsyncSession, fast_client: httpx.AsyncClient, three_ages: dict[str, object]
) -> None:
    """Without a cutoff it is a pure fill: only the never-touched drug, as before -- so
    the refresh behaviour is opt-in and does not change the plain warm pass."""
    _mock_sources_down()

    stats = await enrich_catalog(session, client=fast_client, only_unenriched=True)

    assert stats.drugs == 1  # only CHEMBL_NULL
    stale = await session.get(Drug, "CHEMBL_STALE")
    assert stale is not None
    await session.refresh(stale)
    # The stale drug keeps its old timestamp: no cutoff means no refresh.
    assert stale.last_enriched_at is not None and stale.last_enriched_at < utcnow() - timedelta(
        days=30
    )
