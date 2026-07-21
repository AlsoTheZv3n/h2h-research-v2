"""The PubTator adapter (#44): the Entrez-confirmed gene join, the relation split, and the disease
link -- the pieces that keep an EXTRACTED relation honest and joined by ID, not by name."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
import respx

from backend.ingestion import pubtator

API = pubtator.PUBTATOR_API

# autocomplete responses keyed by the `query` param, and relations keyed by the `e1` param.
_AUTOCOMPLETE: dict[str, list[dict[str, Any]]] = {
    "BRAF": [
        {"_id": "@GENE_BRAF", "biotype": "gene", "db": "ncbi_gene", "db_id": "673", "name": "BRAF"},
        # a paralog with a DIFFERENT entrez -- must be rejected by the confirm step.
        {
            "_id": "@GENE_BRAFP1",
            "biotype": "gene",
            "db": "ncbi_gene",
            "db_id": "9",
            "name": "BRAFP1",
        },
    ],
    "Melanoma": [
        {"_id": "@DISEASE_Melanoma", "biotype": "disease", "db": "ncbi_mesh", "db_id": "D008545"}
    ],
    "Rare Thing": [
        {"_id": "@DISEASE_Rare_Thing", "biotype": "disease", "db": "ncbi_mesh", "db_id": "D999999"}
    ],
}
_RELATIONS: dict[str, list[dict[str, Any]]] = {
    "@GENE_BRAF": [
        {
            "type": "associate",
            "source": "@DISEASE_Melanoma",
            "target": "@GENE_BRAF",
            "publications": 5001,
        },
        {
            "type": "associate",
            "source": "@DISEASE_Rare_Thing",
            "target": "@GENE_BRAF",
            "publications": 40,
        },
        {
            "type": "negative_correlate",
            "source": "@CHEMICAL_Vemurafenib",
            "target": "@GENE_BRAF",
            "publications": 1285,
        },
        {
            "type": "associate",
            "source": "@GENE_MAP2K1",
            "target": "@GENE_BRAF",
            "publications": 300,
        },  # gene-gene: skipped
    ],
}
# Melanoma bridges to a catalog MONDO; Rare Thing does not (unlinked, never mislinked).
_MESH_MAP = {"D008545": ("MONDO_0005105", "melanoma")}


def _mock_api() -> None:
    def autocomplete(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("query", "")
        return httpx.Response(200, json=_AUTOCOMPLETE.get(q, []))

    def relations(request: httpx.Request) -> httpx.Response:
        e1 = request.url.params.get("e1", "")
        return httpx.Response(200, json=_RELATIONS.get(e1, []))

    respx.get(url__startswith=f"{API}/entity/autocomplete/").mock(side_effect=autocomplete)
    respx.get(url__startswith=f"{API}/relations").mock(side_effect=relations)


class TestResolveGeneEntity:
    @respx.mock
    async def test_confirms_the_gene_by_entrez_rejecting_a_paralog(self) -> None:
        _mock_api()
        async with httpx.AsyncClient() as client:
            # entrez 673 -> the real BRAF entity, not the paralog (entrez 9).
            assert await pubtator.resolve_gene_entity(client, "BRAF", 673) == "@GENE_BRAF"

    @respx.mock
    async def test_returns_none_when_no_candidate_matches_our_entrez(self) -> None:
        _mock_api()
        async with httpx.AsyncClient() as client:
            # a symbol whose PubTator gene has a different entrez than ours -> no confirmed join.
            assert await pubtator.resolve_gene_entity(client, "BRAF", 999999) is None

    async def test_no_symbol_makes_no_call(self) -> None:
        async with httpx.AsyncClient() as client:
            assert await pubtator.resolve_gene_entity(client, "", 673) is None


class TestFetchGeneRelations:
    @respx.mock
    async def test_splits_diseases_and_chemicals_and_links_a_bridged_disease(self) -> None:
        _mock_api()
        async with httpx.AsyncClient() as client:
            data = cast(
                dict[str, Any], await pubtator.fetch_gene_relations(client, "BRAF", 673, _MESH_MAP)
            )
        diseases = {d["name"]: d for d in data["diseases"]}
        chemicals = {c["name"]: c for c in data["chemicals"]}
        # gene-gene relation (MAP2K1) is dropped; disease + chemical are kept and split.
        assert set(diseases) == {"Melanoma", "Rare Thing"}
        assert set(chemicals) == {"Vemurafenib"}
        # ordered by co-mention volume; the count is carried as VOLUME, not weight.
        assert data["diseases"][0]["name"] == "Melanoma"
        assert diseases["Melanoma"]["co_mentions"] == 5001
        # THE JOIN: Melanoma's MeSH bridges to a catalog MONDO -> linked; Rare Thing does not.
        assert diseases["Melanoma"]["mondo_id"] == "MONDO_0005105"
        assert diseases["Rare Thing"]["mondo_id"] is None
        # the totals are over ALL relations, not just the shown top.
        assert data["n_disease_relations"] == 2
        assert data["n_chemical_relations"] == 1

    @respx.mock
    async def test_a_gene_pubtator_cannot_confirm_returns_none(self) -> None:
        _mock_api()
        async with httpx.AsyncClient() as client:
            assert await pubtator.fetch_gene_relations(client, "BRAF", 999999, _MESH_MAP) is None

    @respx.mock
    async def test_an_outage_raises_never_a_silent_empty(self) -> None:
        respx.get(url__startswith=f"{API}/entity/autocomplete/").mock(
            return_value=httpx.Response(200, json=_AUTOCOMPLETE["BRAF"])
        )
        respx.get(url__startswith=f"{API}/relations").mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as client:
            with pytest.raises(pubtator.PubtatorError):
                await pubtator.fetch_gene_relations(client, "BRAF", 673, _MESH_MAP)

    def test_provenance_and_citation_constants(self) -> None:
        assert "not curated" in pubtator.EXTRACTED_PROVENANCE
        assert "PubTator" in pubtator.PUBTATOR_CITATION
        assert "National Library of Medicine" in pubtator.PUBTATOR_CITATION
