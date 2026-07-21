"""The target-side cBioPortal reflection (#43): a gene's mutation frequency across the cancers it
drives. Honest states kept apart -- no_cohort (short-circuits before any network call),
gene_unmapped, measured per cohort, and a per-cohort source_failed that never sinks the others."""

from __future__ import annotations

from typing import Any, cast

import httpx
import respx

from backend.ingestion.base import FactStatus
from backend.ingestion.enrich_target import target_alteration_frequency
from backend.models import Target

MYGENE = "https://mygene.info/v3/query"
API = "https://www.cbioportal.org/api"

BRAF = "ENSG00000157764"
SKCM = "skcm_tcga_pan_can_atlas_2018"
LUAD = "luad_tcga_pan_can_atlas_2018"

# Two cancers this gene drives, both with a curated cohort.
CANCERS = [
    {"disease_id": "MONDO_0005012", "name": "cutaneous melanoma", "score": 0.9},
    {"disease_id": "MONDO_0005061", "name": "lung adenocarcinoma", "score": 0.8},
]
STUDY_MAP = {
    "MONDO_0005012": (SKCM, "Cutaneous Melanoma — TCGA PanCancer Atlas"),
    "MONDO_0005061": (LUAD, "Lung Adenocarcinoma — TCGA PanCancer Atlas"),
}


def _target() -> Target:
    return Target(ensembl_id=BRAF, symbol="BRAF")


def _mygene(mapping: dict[str, int]) -> httpx.Response:
    return httpx.Response(200, json=[{"query": e, "entrezgene": g} for e, g in mapping.items()])


def _mock_study(study_id: str, *, sequenced: int, entrez: int, altered: int) -> None:
    respx.get(f"{API}/studies/{study_id}").mock(
        return_value=httpx.Response(
            200,
            json={
                "studyId": study_id,
                "name": study_id,
                "citation": "TCGA, Cell 2018",
                "pmid": "29625048",
                "publicStudy": True,
                "readPermission": True,
            },
        )
    )
    respx.get(f"{API}/sample-lists/{study_id}_sequenced").mock(
        return_value=httpx.Response(200, json={"sampleIds": [f"S{i}" for i in range(sequenced)]})
    )
    respx.post(f"{API}/molecular-profiles/{study_id}_mutations/mutations/fetch").mock(
        return_value=httpx.Response(
            200, json=[{"entrezGeneId": entrez, "sampleId": f"S{i}"} for i in range(altered)]
        )
    )


class TestTargetAlterationFrequency:
    @respx.mock
    async def test_no_cohort_short_circuits_before_any_network_call(self) -> None:
        # Cancers present, but NONE mapped to a cohort -> no_cohort, and NO HTTP call. @respx.mock
        # with an empty route table enforces it: a stray call raises (assert-all-mocked), catching a
        # regression that hits the network before the short-circuit.
        async with httpx.AsyncClient() as client:
            record = await target_alteration_frequency(client, _target(), CANCERS, {})
        fact = record.facts["target_alteration_frequency"]
        assert fact.status is FactStatus.OK
        assert fact.value == {"state": "no_cohort"}

    @respx.mock
    async def test_measures_the_gene_across_each_cohort(self) -> None:
        respx.post(MYGENE).mock(return_value=_mygene({BRAF: 673}))
        _mock_study(SKCM, sequenced=440, entrez=673, altered=233)  # 53.0%
        _mock_study(LUAD, sequenced=566, entrez=673, altered=40)  # 7.1%

        async with httpx.AsyncClient() as client:
            record = await target_alteration_frequency(client, _target(), CANCERS, STUDY_MAP)

        value = cast(dict[str, Any], record.facts["target_alteration_frequency"].value)
        assert value["state"] == "measured"
        assert value["entrez_id"] == 673
        assert "mutation" in value["alteration_scope"].lower()
        by_cancer = {c["name"]: c for c in value["cancers"]}
        assert by_cancer["cutaneous melanoma"]["pct"] == 53.0
        assert by_cancer["cutaneous melanoma"]["state"] == "measured"
        assert by_cancer["lung adenocarcinoma"]["pct"] == 7.1
        assert len(value["attribution"]["portal"]) == 3

    @respx.mock
    async def test_a_gene_that_does_not_resolve_is_gene_unmapped(self) -> None:
        respx.post(MYGENE).mock(
            return_value=httpx.Response(200, json=[{"query": BRAF, "notfound": True}])
        )
        async with httpx.AsyncClient() as client:
            record = await target_alteration_frequency(client, _target(), CANCERS, STUDY_MAP)
        assert record.facts["target_alteration_frequency"].value == {"state": "gene_unmapped"}

    @respx.mock
    async def test_one_cohort_outage_is_source_failed_and_the_others_stand(self) -> None:
        respx.post(MYGENE).mock(return_value=_mygene({BRAF: 673}))
        _mock_study(SKCM, sequenced=440, entrez=673, altered=233)
        respx.get(f"{API}/studies/{LUAD}").mock(return_value=httpx.Response(503))

        async with httpx.AsyncClient() as client:
            record = await target_alteration_frequency(client, _target(), CANCERS, STUDY_MAP)

        value = cast(dict[str, Any], record.facts["target_alteration_frequency"].value)
        by_cancer = {c["name"]: c for c in value["cancers"]}
        assert by_cancer["cutaneous melanoma"]["state"] == "measured"
        assert by_cancer["lung adenocarcinoma"]["state"] == "source_failed"
        assert "pct" not in by_cancer["lung adenocarcinoma"]
