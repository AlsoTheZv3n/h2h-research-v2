"""Target detail read API, against a real Postgres.

Same promise as the drug and cancer briefs: a fact arrives with its source and status, an
outage is flagged unavailable rather than read as an absence, and the associated cancers are
the ones we actually list (every one a live link).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.cache import get_redis, target_detail_cache_key
from backend.ingestion.base import SourceRecord, fact, failed, utcnow
from backend.models import DataMaturity
from backend.repositories import DrugRepository
from backend.repositories.targets import TargetRepository
from backend.services import target_briefs

# The `api` fixture lives in conftest.py.

_TARGET = "ENSG00000133703"  # KRAS
_LUNG = "MONDO_0005233"


def _associated_cancers() -> dict[str, Any]:
    return {
        "n_cancers": 1,
        "cancers": [{"disease_id": _LUNG, "name": "non-small cell lung carcinoma", "score": 0.85}],
    }


@pytest.fixture
async def seeded(db_engine: AsyncEngine) -> None:
    """An enriched target with an associated-cancers fact and one catalog drug against it.

    last_enriched_at is set, because it has been enriched -- that is what having facts means.
    Without it the API reads it as never-analyzed, fires a lazy enrichment at the real Open
    Targets from inside the test, and declines to cache.
    """
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        targets = TargetRepository(s)
        await targets.upsert_target(
            _TARGET,
            symbol="KRAS",
            name="KRAS proto-oncogene",
            n_cancers=1,
            last_enriched_at=utcnow(),
        )
        await targets.save_record(
            _TARGET,
            SourceRecord(
                "opentargets",
                _TARGET,
                ok=True,
                facts={"associated_cancers": fact(_associated_cancers(), "opentargets")},
            ),
        )
        # A catalog drug that acts on this target -> catalog_drugs should link it.
        drugs = DrugRepository(s)
        await drugs.upsert_drug(
            "CHEMBL_KRASI",
            pref_name="sotorasib",
            maturity=DataMaturity.FULL,
            last_enriched_at=utcnow(),
        )
        await drugs.sync_drug_targets("CHEMBL_KRASI", [_TARGET])

        # A second target whose only source FAILED -> its fact key must read as unavailable.
        await targets.upsert_target("ENSG_FAILED", symbol="FAKE", last_enriched_at=utcnow())
        await targets.save_record(
            "ENSG_FAILED",
            SourceRecord(
                "opentargets",
                "ENSG_FAILED",
                ok=True,
                facts={"associated_cancers": failed("opentargets", "OT 503")},
            ),
        )
        await s.commit()


async def test_detail_returns_brief_with_facts_and_catalog_drugs(
    api: httpx.AsyncClient, seeded: None
) -> None:
    r = await api.get(f"/targets/{_TARGET}")
    assert r.status_code == 200
    body = r.json()

    assert body["ensembl_id"] == _TARGET
    assert body["symbol"] == "KRAS"
    assert body["name"] == "KRAS proto-oncogene"
    assert body["n_cancers"] == 1
    assert body["state"] == "ready"

    ac = body["facts"]["associated_cancers"][0]
    assert ac["status"] == "ok"
    assert ac["value"]["cancers"][0]["disease_id"] == _LUNG

    # The drug in our catalog that hits this target, joined on the Ensembl id.
    assert body["catalog_drugs"] == ["CHEMBL_KRASI"]
    assert body["unavailable"] == []

    # A READY brief is cached under the versioned key for the next reader.
    assert await get_redis().get(target_detail_cache_key(_TARGET)) is not None


async def test_source_failed_fact_is_flagged_unavailable(
    api: httpx.AsyncClient, seeded: None
) -> None:
    r = await api.get("/targets/ENSG_FAILED")
    assert r.status_code == 200
    body = r.json()
    # An outage is hoisted so a client cannot mistake it for "this target drives no cancers".
    assert body["unavailable"] == ["associated_cancers"]
    assert body["facts"]["associated_cancers"][0]["status"] == "source_failed"


async def test_unknown_target_is_404(api: httpx.AsyncClient, seeded: None) -> None:
    r = await api.get("/targets/ENSG_DOES_NOT_EXIST")
    assert r.status_code == 404


async def test_retry_unknown_target_is_404(api: httpx.AsyncClient, seeded: None) -> None:
    r = await api.post("/targets/ENSG_DOES_NOT_EXIST/retry")
    assert r.status_code == 404


@pytest.fixture
async def no_background_enrich(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Neuter the background task for the endpoint test: we assert the endpoint's own contract
    (cache invalidation + state), not the fetch, which the brief-service tests cover."""

    async def _noop(ensembl_id: str, maker: object) -> None:
        return None

    monkeypatch.setattr(target_briefs, "_enrich_in_background", _noop)
    yield


async def test_retry_invalidates_the_cached_brief_and_reports_enriching(
    api: httpx.AsyncClient, session: AsyncSession, no_background_enrich: None
) -> None:
    await TargetRepository(session).upsert_target("ENSG_C", symbol="C", last_enriched_at=utcnow())
    await session.commit()

    # A stale cached brief sits in front of the reader.
    cache_key = target_detail_cache_key("ENSG_C")
    await get_redis().set(cache_key, '{"stale": true}')
    assert await get_redis().get(cache_key) is not None

    r = await api.post("/targets/ENSG_C/retry")
    assert r.status_code == 200
    assert r.json()["state"] == "enriching"
    # The stale copy is gone, or the retry would re-fetch behind a cache that keeps serving the
    # old, still-failed brief until the TTL.
    assert await get_redis().get(cache_key) is None
