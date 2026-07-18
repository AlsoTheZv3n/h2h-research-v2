"""The cancer catalog: the loader's real-hit filter, the repository's SQL, the API.

Same discipline as the drug side. The loader test runs the real load_catalog through a
faked Open Targets (httpx.MockTransport) on an unseeded database: only the network is a
stand-in, so a wiring break -- a filter that stops pruning, an upsert that never fires
-- fails it. The repository tests assert filter/sort/count happen in SQL, and each is
built to go red if its clause becomes a no-op.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import pytest

from backend.ingestion import cancer_catalog
from backend.repositories.cancers import CancerRepository


def _ot_transport(
    descendants: list[str], diseases: dict[str, dict[str, Any]]
) -> httpx.MockTransport:
    """A fake Open Targets: answers the descendants query, then per-id batch queries.

    Ids present in `descendants` but absent from `diseases` come back null -- an
    obsolete descendant the loader must drop, exactly as the live API returns them.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)["query"]
        if "descendants" in query:
            return httpx.Response(200, json={"data": {"disease": {"descendants": descendants}}})
        ids = re.findall(r'disease\(efoId:"([^"]+)"\)', query)
        data: dict[str, Any] = {}
        for i, did in enumerate(ids):
            d = diseases.get(did)
            data[f"d{i}"] = (
                None
                if d is None
                else {
                    "id": did,
                    "name": d["name"],
                    "therapeuticAreas": d.get("areas", []),
                    "drugs": {"count": d["drugs"]},
                    "targets": {"count": d["targets"]},
                }
            )
        return httpx.Response(200, json={"data": data})

    return httpx.MockTransport(handler)


# One of each case the seed rule has to get right.
_DISEASES = {
    "MONDO_A": {  # drugs and targets, two areas -> the specific one wins
        "name": "lung cancer",
        "areas": [{"name": "respiratory or thoracic disease"}, {"name": "cancer or benign tumor"}],
        "drugs": 5,
        "targets": 100,
    },
    "MONDO_B": {  # no drugs, some targets -> kept on the target signal; only generic area
        "name": "rare tumor",
        "areas": [{"name": "cancer or benign tumor"}],
        "drugs": 0,
        "targets": 3,
    },
    "MONDO_C": {  # nothing at all -> pruned
        "name": "empty rollup",
        "areas": [{"name": "cancer or benign tumor"}],
        "drugs": 0,
        "targets": 0,
    },
    "MONDO_D": {  # drugs only, no areas -> kept, area None
        "name": "drugged only",
        "areas": [],
        "drugs": 2,
        "targets": 0,
    },
}
# MONDO_X is a descendant Open Targets no longer resolves (returns null).
_DESCENDANTS = ["MONDO_A", "MONDO_B", "MONDO_C", "MONDO_D", "MONDO_X"]


async def test_loader_keeps_real_hits_and_prunes_the_empty(session: Any) -> None:
    client = httpx.AsyncClient(transport=_ot_transport(_DESCENDANTS, _DISEASES))
    try:
        stats = await cancer_catalog.load_catalog(session, client=client)
    finally:
        await client.aclose()

    repo = CancerRepository(session)
    rows, total = await repo.list_cancers(limit=100)
    loaded = {c.disease_id for c in rows}

    # C (0 drugs, 0 targets) pruned; X (unresolved) dropped; A, B, D kept.
    assert loaded == {"MONDO_A", "MONDO_B", "MONDO_D"}
    assert total == 3
    assert stats.descendants == 5
    assert stats.resolved == 4  # A, B, C, D resolved; X came back null
    assert stats.loaded == 3
    assert stats.pruned == 1


async def test_loader_maps_columns_and_picks_the_specific_area(session: Any) -> None:
    client = httpx.AsyncClient(transport=_ot_transport(_DESCENDANTS, _DISEASES))
    try:
        await cancer_catalog.load_catalog(session, client=client)
    finally:
        await client.aclose()

    repo = CancerRepository(session)
    a = await repo.get("MONDO_A")
    b = await repo.get("MONDO_B")
    d = await repo.get("MONDO_D")
    assert a is not None and b is not None and d is not None

    assert (a.n_drugs, a.n_targets) == (5, 100)
    # The specific organ-system area beats the generic "cancer or benign tumor".
    assert a.therapeutic_area == "respiratory or thoracic disease"
    # Only the generic area available -> it is used rather than inventing None.
    assert b.therapeutic_area == "cancer or benign tumor"
    # No area at all -> None, honestly.
    assert d.therapeutic_area is None
    # Never enriched by the loader: the catalog leaves the brief clock NULL.
    assert a.last_enriched_at is None


async def _seed(repo: CancerRepository) -> None:
    await repo.upsert_cancer(
        "MONDO_1",
        name="lung cancer",
        therapeutic_area="respiratory or thoracic disease",
        n_drugs=40,
        n_targets=500,
    )
    await repo.upsert_cancer(
        "MONDO_2",
        name="breast cancer",
        therapeutic_area="reproductive system disease",
        n_drugs=30,
        n_targets=400,
    )
    await repo.upsert_cancer(
        "MONDO_3",
        name="rare lung tumor",
        therapeutic_area="respiratory or thoracic disease",
        n_drugs=0,
        n_targets=7,
    )
    await repo.upsert_cancer(
        "MONDO_4",
        name="melanoma",
        therapeutic_area="integumentary system disorder",
        n_drugs=12,
        n_targets=200,
    )
    await repo.upsert_cancer(
        "MONDO_5", name="obscure carcinoma", therapeutic_area=None, n_drugs=0, n_targets=1
    )


async def test_repo_search_is_a_substring_over_name_and_id(session: Any) -> None:
    repo = CancerRepository(session)
    await _seed(repo)
    rows, total = await repo.list_cancers(q="lung")
    names = {c.name for c in rows}
    # Matches "lung cancer" and "rare lung tumor", nothing else.
    assert names == {"lung cancer", "rare lung tumor"}
    assert total == 2


async def test_repo_has_drugs_filters_to_drugged_cancers(session: Any) -> None:
    repo = CancerRepository(session)
    await _seed(repo)
    with_drugs, total_with = await repo.list_cancers(has_drugs=True)
    without, total_without = await repo.list_cancers(has_drugs=False)
    assert {c.disease_id for c in with_drugs} == {"MONDO_1", "MONDO_2", "MONDO_4"}
    assert total_with == 3
    # The complement, not everything: MONDO_3 and MONDO_5 have 0 drugs.
    assert {c.disease_id for c in without} == {"MONDO_3", "MONDO_5"}
    assert total_without == 2


async def test_repo_area_filter_is_exact(session: Any) -> None:
    repo = CancerRepository(session)
    await _seed(repo)
    rows, total = await repo.list_cancers(therapeutic_area="respiratory or thoracic disease")
    assert {c.disease_id for c in rows} == {"MONDO_1", "MONDO_3"}
    assert total == 2


async def test_repo_sort_by_drugs_orders_and_reverses(session: Any) -> None:
    repo = CancerRepository(session)
    await _seed(repo)
    desc, _ = await repo.list_cancers(sort="drugs", order="desc")
    asc, _ = await repo.list_cancers(sort="drugs", order="asc")
    assert [c.n_drugs for c in desc] == sorted([c.n_drugs for c in desc], reverse=True)
    assert [c.n_drugs for c in asc] == sorted([c.n_drugs for c in asc])
    # A real flip: the single most-drugged cancer sits at the top of desc and the
    # bottom of asc. (Full-list reversal would not hold -- the disease_id tiebreaker
    # runs the same way in both directions, so tied 0-drug rows keep their order.)
    assert desc[0].disease_id == asc[-1].disease_id
    assert desc[0].disease_id != asc[0].disease_id


async def test_repo_total_counts_the_filtered_set_not_the_page(session: Any) -> None:
    repo = CancerRepository(session)
    await _seed(repo)
    rows, total = await repo.list_cancers(limit=2)
    # Five seeded, one page of two: the total is the catalog, not the page length.
    assert len(rows) == 2
    assert total == 5


async def test_repo_area_facet_lists_present_areas_by_frequency(session: Any) -> None:
    repo = CancerRepository(session)
    await _seed(repo)
    areas = await repo.distinct_therapeutic_areas()
    # "respiratory or thoracic disease" appears twice, so it leads; None is excluded.
    assert areas[0] == "respiratory or thoracic disease"
    assert None not in areas
    assert "reproductive system disease" in areas


async def test_api_lists_filters_and_counts(api: httpx.AsyncClient, session: Any) -> None:
    await _seed(CancerRepository(session))
    await session.commit()

    everything = (await api.get("/cancers")).json()
    assert everything["total"] == 5
    assert {c["disease_id"] for c in everything["items"]} == {f"MONDO_{i}" for i in range(1, 6)}

    lung = (await api.get("/cancers", params={"q": "lung"})).json()
    assert lung["total"] == 2

    drugged = (await api.get("/cancers", params={"has_drugs": "true"})).json()
    assert drugged["total"] == 3
    assert all(c["n_drugs"] > 0 for c in drugged["items"])


async def test_api_detail_is_not_analyzed_until_enriched(
    api: httpx.AsyncClient, session: Any
) -> None:
    await _seed(CancerRepository(session))
    await session.commit()

    detail = (await api.get("/cancers/MONDO_1")).json()
    assert detail["name"] == "lung cancer"
    assert detail["n_drugs"] == 40
    # No enrich_cancer job yet: the honest state is not_analyzed, never "ready".
    assert detail["state"] == "not_analyzed"

    assert (await api.get("/cancers/MONDO_nope")).status_code == 404


async def test_api_area_facet_endpoint(api: httpx.AsyncClient, session: Any) -> None:
    await _seed(CancerRepository(session))
    await session.commit()
    areas = (await api.get("/cancers/therapeutic-areas")).json()
    assert "respiratory or thoracic disease" in areas
    # The path is not swallowed by /{disease_id}: it returns the facet, not a 404.
    assert isinstance(areas, list)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
