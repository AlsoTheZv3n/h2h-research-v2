"""Target enrichment: the Open Targets reverse query, filtered to our cancer catalog.

Drives the real enrich_target against a real database with Open Targets mocked at the HTTP
boundary. Pins the invariants that make a target brief honest: the reverse query returns a
target's associated diseases (cancers AND non-cancers), and only the diseases we actually list
survive; an outage becomes a source_failed fact and does NOT blank the last measured name /
n_cancers; a target Open Targets cannot resolve writes no fact (never a measured "no cancers");
and a resolved target with no catalog cancers is a measured EMPTY with n_cancers == 0.
"""

from __future__ import annotations

from typing import Any

import httpx
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import FactStatus
from backend.ingestion.enrich_target import (
    _TOP_CANCERS,
    TargetEnrichStats,
    enrich_target,
    opentargets_associated_cancers,
)
from backend.models import Target
from backend.repositories.cancers import CancerRepository
from backend.repositories.targets import TargetRepository

OT = "https://api.platform.opentargets.org/api/v4/graphql"
MYGENE = "https://mygene.info/v3/query"


def _mock_mygene_empty() -> None:
    # The #44 extracted-relations source resolves the gene's Entrez via mygene before it can reach
    # PubTator; an empty response short-circuits it to a gene_unmapped fact, so these tests (about
    # the associated-cancers source) never hit the PubTator network. Registered only where a target
    # resolves (record.ok) and the source therefore runs.
    respx.post(MYGENE).mock(return_value=httpx.Response(200, json=[]))


# Two cancers in our catalog + one non-cancer (a RASopathy) that is NOT -- the exact shape the
# filter must handle: KRAS-style, where a syndrome outscores the cancers.
_LUNG = "MONDO_0005233"
_BREAST = "MONDO_0007254"
_NOONAN = "MONDO_0018997"  # deliberately NOT seeded into the catalog


def _ot_response(
    rows: list[dict[str, Any]], approved_name: str = "KRAS proto-oncogene"
) -> dict[str, Any]:
    return {
        "data": {
            "target": {
                "id": "ENSG_TEST",
                "approvedSymbol": "KRAS",
                "approvedName": approved_name,
                "associatedDiseases": {"count": len(rows), "rows": rows},
            }
        }
    }


def _row(disease_id: str, name: str, score: float) -> dict[str, Any]:
    return {"score": score, "disease": {"id": disease_id, "name": name}}


async def _seed_catalog(session: AsyncSession) -> set[str]:
    """Two cancers in the catalog (Noonan is deliberately absent)."""
    cancers = CancerRepository(session)
    await cancers.upsert_cancer(_LUNG, name="non-small cell lung carcinoma", n_drugs=1, n_targets=1)
    await cancers.upsert_cancer(_BREAST, name="breast carcinoma", n_drugs=1, n_targets=1)
    await session.commit()
    return await cancers.all_cancer_ids()


@respx.mock
async def test_filters_associated_diseases_to_catalog_cancers(
    session: AsyncSession, fast_client: httpx.AsyncClient
) -> None:
    catalog_ids = await _seed_catalog(session)
    # Noonan outscores the cancers (the case the filter exists for), AND the rows are input
    # deliberately NOT score-sorted (breast 0.70 before lung 0.85), so the assertion below
    # proves the code's own rows.sort(), not the fixture order.
    rows = [
        _row(_BREAST, "breast carcinoma", 0.70),
        _row(_NOONAN, "Noonan syndrome", 0.91),
        _row(_LUNG, "non-small cell lung carcinoma", 0.85),
    ]
    respx.post(OT).mock(return_value=httpx.Response(200, json=_ot_response(rows)))

    target = Target(ensembl_id="ENSG_TEST", symbol="KRAS")
    result = await opentargets_associated_cancers(fast_client, target, catalog_ids)

    fact = result.record.facts["associated_cancers"]
    assert fact.status is FactStatus.OK
    assert isinstance(fact.value, dict)
    # Noonan is dropped; the two catalog cancers survive, re-ordered score-descending by the
    # code (lung 0.85 before breast 0.70, the reverse of the input order).
    assert [c["disease_id"] for c in fact.value["cancers"]] == [_LUNG, _BREAST]
    assert fact.value["n_cancers"] == 2
    assert result.n_cancers == 2
    assert result.approved_name == "KRAS proto-oncogene"


@respx.mock
async def test_n_cancers_counts_all_catalog_cancers_but_display_is_capped(
    session: AsyncSession, fast_client: httpx.AsyncClient
) -> None:
    # More catalog cancers than the display cap: n_cancers must be the FULL filtered count,
    # while the stored `cancers` list is capped at the top _TOP_CANCERS by score. A count/slice
    # mix-up (counting the slice) or an uncapped display would be caught here.
    cancers = CancerRepository(session)
    n = _TOP_CANCERS + 5
    ids = [f"MONDO_{i:07d}" for i in range(1, n + 1)]
    for did in ids:
        await cancers.upsert_cancer(did, name=f"cancer {did}", n_drugs=1, n_targets=1)
    await session.commit()
    catalog_ids = await cancers.all_cancer_ids()

    # Input score-descending so the top-N slice is well defined; every one is in the catalog.
    rows = [_row(did, f"cancer {did}", round(0.99 - i * 0.001, 4)) for i, did in enumerate(ids)]
    respx.post(OT).mock(return_value=httpx.Response(200, json=_ot_response(rows)))

    target = Target(ensembl_id="ENSG_TEST", symbol="KRAS")
    result = await opentargets_associated_cancers(fast_client, target, catalog_ids)

    fact = result.record.facts["associated_cancers"]
    assert isinstance(fact.value, dict)
    assert fact.value["n_cancers"] == n  # counts ALL filtered cancers, not just the shown slice
    assert result.n_cancers == n
    assert len(fact.value["cancers"]) == _TOP_CANCERS  # display capped at the top N
    assert fact.value["cancers"][0]["disease_id"] == ids[0]  # highest score leads


@respx.mock
async def test_enrich_sets_catalog_row_and_persists_fact(
    session: AsyncSession, fast_client: httpx.AsyncClient
) -> None:
    catalog_ids = await _seed_catalog(session)
    repo = TargetRepository(session)
    await repo.upsert_target("ENSG_TEST", symbol="KRAS")
    await session.commit()

    rows = [_row(_LUNG, "non-small cell lung carcinoma", 0.85)]
    respx.post(OT).mock(return_value=httpx.Response(200, json=_ot_response(rows)))

    target = await repo.get("ENSG_TEST")
    assert target is not None
    _mock_mygene_empty()
    await enrich_target(session, target, fast_client, catalog_ids, {}, {}, TargetEnrichStats())
    await session.commit()

    refreshed = await repo.get("ENSG_TEST")
    assert refreshed is not None
    assert refreshed.name == "KRAS proto-oncogene"
    assert refreshed.n_cancers == 1
    assert refreshed.last_enriched_at is not None
    facts = {f.key: f for f in await repo.facts_for("ENSG_TEST")}
    assert facts["associated_cancers"].status is FactStatus.OK


@respx.mock
async def test_outage_is_source_failed_and_preserves_prior_counts(
    session: AsyncSession, fast_client: httpx.AsyncClient
) -> None:
    catalog_ids = await _seed_catalog(session)
    repo = TargetRepository(session)
    await repo.upsert_target("ENSG_TEST", symbol="KRAS")
    await session.commit()
    target = await repo.get("ENSG_TEST")
    assert target is not None

    # First enrich: OK, two cancers -> name + n_cancers measured and stored.
    ok_rows = [_row(_LUNG, "lung", 0.85), _row(_BREAST, "breast", 0.70)]
    respx.post(OT).mock(return_value=httpx.Response(200, json=_ot_response(ok_rows)))
    _mock_mygene_empty()
    await enrich_target(session, target, fast_client, catalog_ids, {}, {}, TargetEnrichStats())
    await session.commit()

    # Then an outage: the fact becomes source_failed, but name / n_cancers must survive (they
    # were not remeasured -- None, not a new value), and last_enriched_at still advances.
    respx.post(OT).mock(return_value=httpx.Response(503, text="Service Unavailable"))
    await enrich_target(session, target, fast_client, catalog_ids, {}, {}, TargetEnrichStats())
    await session.commit()

    refreshed = await repo.get("ENSG_TEST")
    assert refreshed is not None
    assert refreshed.n_cancers == 2  # preserved, NOT blanked by the outage
    assert refreshed.name == "KRAS proto-oncogene"
    facts = {f.key: f for f in await repo.facts_for("ENSG_TEST")}
    assert facts["associated_cancers"].status is FactStatus.SOURCE_FAILED


@respx.mock
async def test_unresolved_target_writes_no_fact(
    session: AsyncSession, fast_client: httpx.AsyncClient
) -> None:
    catalog_ids = await _seed_catalog(session)
    repo = TargetRepository(session)
    await repo.upsert_target("ENSG_TEST", symbol="KRAS")
    await session.commit()
    target = await repo.get("ENSG_TEST")
    assert target is not None

    # Open Targets answers but does not resolve the id -> target: null. NOT "no cancers": no
    # fact is written, so nothing claims this target drives nothing.
    respx.post(OT).mock(return_value=httpx.Response(200, json={"data": {"target": None}}))
    await enrich_target(session, target, fast_client, catalog_ids, {}, {}, TargetEnrichStats())
    await session.commit()

    assert await repo.facts_for("ENSG_TEST") == []
    refreshed = await repo.get("ENSG_TEST")
    assert refreshed is not None
    assert refreshed.last_enriched_at is not None  # we looked
    assert refreshed.n_cancers is None  # never measured -- NULL, not 0


@respx.mock
async def test_no_catalog_cancers_is_measured_empty(
    session: AsyncSession, fast_client: httpx.AsyncClient
) -> None:
    catalog_ids = await _seed_catalog(session)
    repo = TargetRepository(session)
    await repo.upsert_target("ENSG_TEST", symbol="KRAS")
    await session.commit()
    target = await repo.get("ENSG_TEST")
    assert target is not None

    # Resolved, but every associated disease is a non-cancer we do not list -> measured EMPTY,
    # n_cancers == 0 (a real zero: enriched, none in our catalog), distinct from NULL.
    respx.post(OT).mock(
        return_value=httpx.Response(200, json=_ot_response([_row(_NOONAN, "Noonan", 0.9)]))
    )
    _mock_mygene_empty()
    await enrich_target(session, target, fast_client, catalog_ids, {}, {}, TargetEnrichStats())
    await session.commit()

    facts = {f.key: f for f in await repo.facts_for("ENSG_TEST")}
    assert facts["associated_cancers"].status is FactStatus.EMPTY
    refreshed = await repo.get("ENSG_TEST")
    assert refreshed is not None
    assert refreshed.n_cancers == 0
