"""The target-side PubTator source (#44): its honest states, and the load-bearing 'extracted'
stamp that keeps NLP-extracted relations from ever reading as curated facts."""

from __future__ import annotations

from typing import Any, cast

import httpx
import respx

from backend.ingestion import pubtator
from backend.ingestion.base import FactStatus
from backend.ingestion.enrich_target import target_extracted_relations
from backend.models import Target

MYGENE = "https://mygene.info/v3/query"
API = pubtator.PUBTATOR_API
BRAF = "ENSG00000157764"

_MESH_MAP = {"D008545": ("MONDO_0005105", "melanoma")}


def _target() -> Target:
    return Target(ensembl_id=BRAF, symbol="BRAF")


def _mygene(entrez: int | None) -> httpx.Response:
    return httpx.Response(
        200, json=[{"query": BRAF, "entrezgene": entrez}] if entrez is not None else []
    )


def _mock_pubtator() -> None:
    def autocomplete(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("query", "")
        data = {
            "BRAF": [{"_id": "@GENE_BRAF", "biotype": "gene", "db": "ncbi_gene", "db_id": "673"}],
            "Melanoma": [
                {
                    "_id": "@DISEASE_Melanoma",
                    "biotype": "disease",
                    "db": "ncbi_mesh",
                    "db_id": "D008545",
                }
            ],
        }
        return httpx.Response(200, json=data.get(q, []))

    respx.get(url__startswith=f"{API}/entity/autocomplete/").mock(side_effect=autocomplete)
    respx.get(url__startswith=f"{API}/relations").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "type": "associate",
                    "source": "@DISEASE_Melanoma",
                    "target": "@GENE_BRAF",
                    "publications": 5001,
                },
                {
                    "type": "negative_correlate",
                    "source": "@CHEMICAL_Vemurafenib",
                    "target": "@GENE_BRAF",
                    "publications": 1285,
                },
            ],
        )
    )


class TestTargetExtractedRelations:
    @respx.mock
    async def test_a_gene_that_does_not_resolve_to_entrez_is_gene_unmapped(self) -> None:
        # mygene returns nothing -> no Entrez -> gene_unmapped, and NO PubTator call (unmocked).
        respx.post(MYGENE).mock(return_value=_mygene(None))
        async with httpx.AsyncClient() as client:
            record = await target_extracted_relations(client, _target(), _MESH_MAP)
        assert record.facts["extracted_relations"].value == {"state": "gene_unmapped"}

    @respx.mock
    async def test_extracted_relations_are_stamped_and_the_disease_links(self) -> None:
        respx.post(MYGENE).mock(return_value=_mygene(673))
        _mock_pubtator()
        async with httpx.AsyncClient() as client:
            record = await target_extracted_relations(client, _target(), _MESH_MAP)

        fact = record.facts["extracted_relations"]
        assert fact.status is FactStatus.OK
        assert fact.source == "pubtator"
        value = cast(dict[str, Any], fact.value)
        assert value["state"] == "extracted"
        # THE load-bearing stamp: never blended with curated facts.
        assert "not curated" in value["provenance"]
        assert "PubTator" in value["attribution"]
        diseases = {d["name"]: d for d in value["diseases"]}
        assert diseases["Melanoma"]["mondo_id"] == "MONDO_0005105"  # bridged -> linked
        assert value["chemicals"][0]["name"] == "Vemurafenib"

    @respx.mock
    async def test_an_outage_is_source_failed_never_empty(self) -> None:
        respx.post(MYGENE).mock(return_value=_mygene(673))
        respx.get(url__startswith=f"{API}/entity/autocomplete/").mock(
            return_value=httpx.Response(
                200, json=[{"_id": "@GENE_BRAF", "biotype": "gene", "db_id": "673"}]
            )
        )
        respx.get(url__startswith=f"{API}/relations").mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as client:
            record = await target_extracted_relations(client, _target(), _MESH_MAP)
        fact = record.facts["extracted_relations"]
        assert fact.status is FactStatus.SOURCE_FAILED
        assert record.outage is True

    @respx.mock
    async def test_a_gene_pubtator_cannot_confirm_writes_no_fact(self) -> None:
        # mygene gives an Entrez, but PubTator's gene has a different one -> unconfirmed -> no fact.
        respx.post(MYGENE).mock(return_value=_mygene(673))
        respx.get(url__startswith=f"{API}/entity/autocomplete/").mock(
            return_value=httpx.Response(
                200, json=[{"_id": "@GENE_OTHER", "biotype": "gene", "db_id": "999"}]
            )
        )
        async with httpx.AsyncClient() as client:
            record = await target_extracted_relations(client, _target(), _MESH_MAP)
        assert "extracted_relations" not in record.facts
        assert record.error
