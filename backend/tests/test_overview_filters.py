"""The overview's server-side filters, sort and count, through the real API.

Every filter assertion checks the set actually NARROWS to the right rows, and the
count with it -- because a filter that quietly does nothing is worse than no filter:
it hands the reader a count that is a lie. The no-op guard is explicit throughout
(the filtered set is a proper subset, and the excluded rows really are excluded), so
a filter that stops filtering fails here rather than shipping.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.models import DataMaturity, Drug
from backend.repositories import DrugRepository

# (chembl_id, name, drug_type, maturity, target, phase, target_class, in_scope)
# in_scope None means "not yet judged" -- shown by default, like the bulk of the catalog.
_ROWS = [
    ("CHEMBL_A", "alphamab", "Small molecule", DataMaturity.FULL, "KRAS", 4, "Hydrolase", None),
    ("CHEMBL_B", "betinib", "Small molecule", DataMaturity.PARTIAL, "EGFR", 3, "Kinase", None),
    # No target and no class: the antibody is the "Unclassified" case.
    ("CHEMBL_C", "gammamab", "Antibody", DataMaturity.INDEX_ONLY, None, 4, None, None),
    (
        "CHEMBL_D",
        "deltinib",
        "Small molecule",
        DataMaturity.INDEX_ONLY,
        "KRAS",
        2,
        "Hydrolase",
        None,
    ),
    # Out of scope: a non-oncology false positive. Hidden by default, so every existing
    # count here still reads 4 -- and revealed only with include_out_of_scope.
    ("CHEMBL_E", "epsilonstat", "Small molecule", DataMaturity.INDEX_ONLY, None, 4, None, False),
]


@pytest.fixture
async def catalog(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Seed the fixture drugs, and -- crucially -- delete them afterwards.

    These are seeded through their own sessionmaker rather than the `session` fixture
    (so the `api` client sees committed rows), which means the `session` fixture's
    truncation does not reach them. Without this teardown they leak into later tests:
    they carry no last_enriched_at, so the pre-warmer test that runs after picks them
    up as unenriched and its `stats.drugs == 1` assertion fails. Found by the full
    suite; isolated, both files pass.
    """
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        repo = DrugRepository(s)
        for cid, name, dt, mat, tgt, phase, tclass, in_scope in _ROWS:
            await repo.upsert_drug(
                cid,
                pref_name=name,
                drug_type=dt,
                maturity=mat,
                primary_target=tgt,
                max_phase=phase,
                target_class=tclass,
                in_scope=in_scope,
            )
        await s.commit()
    yield
    async with maker() as s:
        await s.execute(delete(Drug).where(Drug.chembl_id.in_([r[0] for r in _ROWS])))
        await s.commit()


async def _page(api: httpx.AsyncClient, **params: object) -> tuple[set[str], int, list[str]]:
    r = await api.get("/drugs", params={k: str(v) for k, v in params.items()})
    assert r.status_code == 200, r.text
    body = r.json()
    order = [i["chembl_id"] for i in body["items"]]
    return set(order), body["total"], order


async def _facets(api: httpx.AsyncClient, **params: object) -> dict[str, dict[str, int]]:
    r = await api.get("/drugs/facets", params={k: str(v) for k, v in params.items()})
    assert r.status_code == 200, r.text
    return {facet: {o["value"]: o["count"] for o in opts} for facet, opts in r.json().items()}


class TestFilters:
    async def test_modality_narrows_to_only_that_type(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        ids, total, _ = await _page(api, modality="Small molecule")
        assert ids == {"CHEMBL_A", "CHEMBL_B", "CHEMBL_D"}
        assert total == 3
        # Not a no-op: the whole catalog is 4, the antibody is gone, the count shrank.
        all_ids, all_total, _ = await _page(api)
        assert all_total == 4
        assert "CHEMBL_C" in all_ids and "CHEMBL_C" not in ids

    async def test_maturity_filters_by_data_completeness(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        ids, total, _ = await _page(api, maturity="full")
        assert ids == {"CHEMBL_A"} and total == 1
        ids, total, _ = await _page(api, maturity="index_only")
        assert ids == {"CHEMBL_C", "CHEMBL_D"} and total == 2

    async def test_has_target_splits_the_catalog(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        without, wtotal, _ = await _page(api, has_target="false")
        assert without == {"CHEMBL_C"} and wtotal == 1
        witht, ttotal, _ = await _page(api, has_target="true")
        assert witht == {"CHEMBL_A", "CHEMBL_B", "CHEMBL_D"} and ttotal == 3
        # The two halves partition the catalog: nothing lost, nothing double-counted.
        assert wtotal + ttotal == 4

    async def test_target_facet_is_case_insensitive(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        ids, total, _ = await _page(api, target="kras")
        assert ids == {"CHEMBL_A", "CHEMBL_D"} and total == 2

    async def test_filters_compose_in_sql(self, api: httpx.AsyncClient, catalog: None) -> None:
        # small molecule AND KRAS -> A and D, but not the antibody, not EGFR.
        ids, total, _ = await _page(api, modality="Small molecule", target="KRAS")
        assert ids == {"CHEMBL_A", "CHEMBL_D"} and total == 2


class TestTargetClassFacet:
    async def test_class_filter_narrows_to_that_family(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        ids, total, _ = await _page(api, target_class="Hydrolase")
        assert ids == {"CHEMBL_A", "CHEMBL_D"} and total == 2
        # Not a no-op: the Kinase and unclassified rows are really excluded.
        _, all_total, _ = await _page(api)
        assert all_total == 4
        assert {"CHEMBL_B", "CHEMBL_C"}.isdisjoint(ids)

    async def test_class_filter_is_case_insensitive(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        ids, total, _ = await _page(api, target_class="kinase")
        assert ids == {"CHEMBL_B"} and total == 1

    async def test_unclassified_selects_rows_with_no_class(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # "unclassified" is target_class IS NULL, not a literal match on the string --
        # the antibody, which carries no class, is the only such row.
        ids, total, _ = await _page(api, target_class="unclassified")
        assert ids == {"CHEMBL_C"} and total == 1

    async def test_facet_lists_present_classes_most_common_first(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        r = await api.get("/drugs/target-classes")
        assert r.status_code == 200, r.text
        classes = r.json()
        # Hydrolase (2 rows) outranks Kinase (1); NULL is never listed -- the client
        # appends "Unclassified" itself. If the endpoint listed NULL or lost the
        # count-ordering, this fails.
        assert classes == ["Hydrolase", "Kinase"]

    async def test_facet_route_is_not_swallowed_by_the_id_route(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # /drugs/target-classes must not resolve as /drugs/{chembl_id="target-classes"}.
        # A 404 here would mean the path-param route captured it -- a declaration-order
        # regression that a list response quietly hides until you check the shape.
        r = await api.get("/drugs/target-classes")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestFacetCounts:
    async def test_counts_reflect_the_default_in_scope_view(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # Over the 4 in-scope drugs (the out-of-scope E is hidden by default, so it is not counted).
        f = await _facets(api)
        assert f["modality"] == {"Small molecule": 3, "Antibody": 1}
        assert f["maturity"] == {"index_only": 2, "full": 1, "partial": 1}
        # NULL target_class is the real "unclassified" bucket (the antibody), folded to the token.
        assert f["target_class"] == {"Hydrolase": 2, "Kinase": 1, "unclassified": 1}
        assert f["has_target"] == {"true": 3, "false": 1}

    async def test_a_facet_excludes_its_own_selection(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # The load-bearing semantics: with modality=Antibody selected, the MODALITY facet still
        # shows ALL modalities (as if unselected, so a reader can switch), while the OTHER facets
        # are counted among antibodies only (just the antibody CHEMBL_C).
        f = await _facets(api, modality="Antibody")
        assert f["modality"] == {"Small molecule": 3, "Antibody": 1}  # own clause excluded
        assert f["target_class"] == {"unclassified": 1}  # among antibodies
        assert f["has_target"] == {"false": 1}
        assert f["maturity"] == {"index_only": 1}

    async def test_another_facet_narrows_the_counts(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # target_class=Hydrolase -> the two Hydrolase rows (A, D, both Small molecule, both with a
        # target). The MODALITY and HAS_TARGET facets reflect that filter; the TARGET_CLASS facet
        # (its own clause excluded) still shows every class. If facet_counts ignored other filters,
        # modality would read the whole catalog; if it did not exclude its own, target_class would
        # collapse to just Hydrolase.
        f = await _facets(api, target_class="Hydrolase")
        assert f["modality"] == {"Small molecule": 2}
        assert f["has_target"] == {"true": 2}
        assert f["target_class"] == {"Hydrolase": 2, "Kinase": 1, "unclassified": 1}

    async def test_out_of_scope_is_counted_only_when_included(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # The scope boundary is NOT a facet and is never excluded: E (out of scope, Small molecule)
        # is absent by default and joins the Small-molecule count only with include_out_of_scope.
        assert (await _facets(api))["modality"]["Small molecule"] == 3
        f = await _facets(api, include_out_of_scope="true")
        assert f["modality"] == {"Small molecule": 4, "Antibody": 1}

    async def test_facets_route_is_not_swallowed_by_the_id_route(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # /drugs/facets must not resolve as /drugs/{chembl_id="facets"} (declaration-order guard).
        r = await api.get("/drugs/facets")
        assert r.status_code == 200
        assert isinstance(r.json(), dict) and "modality" in r.json()


class TestScopeFilter:
    async def test_out_of_scope_is_hidden_by_default(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # The catalog is oncology: the non-oncology row is absent unless asked for.
        ids, total, _ = await _page(api)
        assert "CHEMBL_E" not in ids
        assert total == 4

    async def test_include_out_of_scope_reveals_them(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        ids, total, _ = await _page(api, include_out_of_scope="true")
        assert "CHEMBL_E" in ids
        assert total == 5
        # Not a no-op the other way: the default really did hide exactly this one.
        default_ids, default_total, _ = await _page(api)
        assert ids - default_ids == {"CHEMBL_E"}
        assert total - default_total == 1

    async def test_null_scope_is_shown_not_hidden(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # in_scope NULL means "not yet judged", and must never be hidden -- an
        # unfinished scoping pass would otherwise blank most of the catalog.
        ids, _, _ = await _page(api)
        assert {"CHEMBL_A", "CHEMBL_B", "CHEMBL_C", "CHEMBL_D"} <= ids


class TestSort:
    async def test_default_sort_is_data_completeness_desc(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        """The drugs a reader can explore right now come first."""
        _, _, order = await _page(api)
        assert order[0] == "CHEMBL_A"  # full
        assert order[1] == "CHEMBL_B"  # partial
        assert set(order[2:]) == {"CHEMBL_C", "CHEMBL_D"}  # index_only, either order

    async def test_sort_by_name_ascending(self, api: httpx.AsyncClient, catalog: None) -> None:
        _, _, order = await _page(api, sort="name", order="asc")
        # alphamab, betinib, deltinib, gammamab
        assert order == ["CHEMBL_A", "CHEMBL_B", "CHEMBL_D", "CHEMBL_C"]

    async def test_sort_by_phase_descending(self, api: httpx.AsyncClient, catalog: None) -> None:
        _, _, order = await _page(api, sort="phase", order="desc")
        assert set(order[:2]) == {"CHEMBL_A", "CHEMBL_C"}  # phase 4
        assert order[2] == "CHEMBL_B"  # phase 3
        assert order[3] == "CHEMBL_D"  # phase 2

    async def test_order_flips_the_result(self, api: httpx.AsyncClient, catalog: None) -> None:
        _, _, asc = await _page(api, sort="phase", order="asc")
        _, _, desc = await _page(api, sort="phase", order="desc")
        # A real sort: reversing the order reverses the ends. D (phase 2) leads asc,
        # trails desc. If order were ignored, these would be identical.
        assert asc[0] == "CHEMBL_D"
        assert desc[-1] == "CHEMBL_D"
        assert asc != desc


class TestCountReflectsFilters:
    async def test_the_count_is_the_filtered_total_not_the_page(
        self, api: httpx.AsyncClient, catalog: None
    ) -> None:
        # A page of 1 over a filtered set of 3 must still report total 3 -- the spike's
        # "page length read as total" bug, guarded at the filter level.
        _, total, order = await _page(api, modality="Small molecule", limit=1)
        assert total == 3
        assert len(order) == 1
