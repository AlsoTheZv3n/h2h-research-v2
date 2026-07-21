"""The cBioPortal adapter + the Ensembl->Entrez resolver (#43).

Fixtures pin the numerator/denominator to the real probe truth (BRAF in TCGA melanoma is 233/440 =
53.0%), so a change to the counting math fails here rather than shipping a wrong percentage. The
honest states get their own tests: a whole-exome gene with no mutations is a MEASURED zero (not
omitted), a non-redistributable study is REFUSED (not fetched), and every outage raises rather than
returning a silent zero.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from backend.ingestion import cbioportal
from backend.ingestion.gene_ids import resolve_entrez

API = "https://www.cbioportal.org/api"
MYGENE = "https://mygene.info/v3/query"
STUDY = "skcm_tcga_pan_can_atlas_2018"


def _study(*, public: bool = True, read: bool = True) -> dict[str, Any]:
    return {
        "studyId": STUDY,
        "name": "Skin Cutaneous Melanoma (TCGA, PanCancer Atlas)",
        "citation": "TCGA, Cell 2018",
        "pmid": "29625048,29596782",
        "publicStudy": public,
        "readPermission": read,
    }


def _sequenced(n: int) -> dict[str, Any]:
    return {"sampleListId": f"{STUDY}_sequenced", "sampleIds": [f"S{i}" for i in range(n)]}


def _muts(counts: dict[int, int]) -> list[dict[str, Any]]:
    """Mutation records for a gene->distinct-sample-count map. Adds a duplicate record for the
    first sample of each gene, so the adapter is exercised on DISTINCT-sample counting, not a raw
    record count."""
    out: list[dict[str, Any]] = []
    for gene, n in counts.items():
        for i in range(n):
            out.append({"entrezGeneId": gene, "sampleId": f"S{i}"})
        if n:
            out.append({"entrezGeneId": gene, "sampleId": "S0"})  # duplicate: same sample again
    return out


def _mock(study: dict[str, Any], sequenced: dict[str, Any], muts: list[dict[str, Any]]) -> None:
    respx.get(f"{API}/studies/{STUDY}").mock(return_value=httpx.Response(200, json=study))
    respx.get(f"{API}/sample-lists/{STUDY}_sequenced").mock(
        return_value=httpx.Response(200, json=sequenced)
    )
    respx.post(f"{API}/molecular-profiles/{STUDY}_mutations/mutations/fetch").mock(
        return_value=httpx.Response(200, json=muts)
    )


class TestMutationFrequencies:
    @respx.mock
    async def test_counts_distinct_samples_and_pins_braf_melanoma_to_the_probe_truth(self) -> None:
        # BRAF (673) mutated in 233 distinct samples of 440 sequenced -> 53.0%, the real figure.
        _mock(_study(), _sequenced(440), _muts({673: 233, 4893: 125}))
        async with httpx.AsyncClient() as client:
            freq = await cbioportal.fetch_mutation_frequencies(client, STUDY, [673, 4893])
        assert freq.denominator == 440
        # distinct samples, not the 234 records (233 + 1 duplicate) we fed for BRAF.
        assert freq.altered_by_entrez[673] == 233
        assert round(100 * freq.altered_by_entrez[673] / freq.denominator, 1) == 53.0
        assert freq.altered_by_entrez[4893] == 125
        # attribution read live off the study object -- the specific source study + first pmid.
        assert freq.study_citation == "TCGA, Cell 2018"
        assert freq.study_pmid == "29625048"
        assert freq.study_name and "Melanoma" in freq.study_name

    @respx.mock
    async def test_a_profiled_gene_with_no_mutations_is_a_measured_zero_not_omitted(self) -> None:
        # TP53 (7157) queried but absent from the records: a whole-exome cohort profiled it, so it
        # is 0 altered / a MEASURED zero -- present with 0, never dropped (which would read as "not
        # measured" one rung up).
        _mock(_study(), _sequenced(440), _muts({673: 233}))
        async with httpx.AsyncClient() as client:
            freq = await cbioportal.fetch_mutation_frequencies(client, STUDY, [673, 7157])
        assert freq.altered_by_entrez[7157] == 0
        assert 7157 in freq.altered_by_entrez

    @respx.mock
    async def test_a_non_redistributable_study_is_refused_not_fetched(self) -> None:
        # The licence guard: a study that reports itself non-public must never be fetched, even if
        # it slipped into the crosswalk. Belt-and-suspenders on the CSV whitelist.
        _mock(_study(public=False), _sequenced(440), _muts({673: 1}))
        async with httpx.AsyncClient() as client:
            with pytest.raises(cbioportal.CBioPortalError, match="not redistributable"):
                await cbioportal.fetch_mutation_frequencies(client, STUDY, [673])

    @respx.mock
    async def test_an_empty_denominator_raises_rather_than_dividing(self) -> None:
        _mock(_study(), _sequenced(0), [])
        async with httpx.AsyncClient() as client:
            with pytest.raises(cbioportal.CBioPortalError, match="no sequenced samples"):
                await cbioportal.fetch_mutation_frequencies(client, STUDY, [673])

    @respx.mock
    async def test_an_outage_raises_and_is_never_a_zero(self) -> None:
        respx.get(f"{API}/studies/{STUDY}").mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as client:
            with pytest.raises(cbioportal.CBioPortalError):
                await cbioportal.fetch_mutation_frequencies(client, STUDY, [673])

    async def test_redistributable_guard_uses_publicstudy_and_vetoes_on_explicit_restriction(
        self,
    ) -> None:
        assert cbioportal.study_is_redistributable(_study()) is True
        # publicStudy is authoritative: absent -> fail closed.
        assert cbioportal.study_is_redistributable({}) is False
        assert cbioportal.study_is_redistributable({"publicStudy": False}) is False
        # publicStudy=True with readPermission omitted is still public (not over-refused)...
        assert cbioportal.study_is_redistributable({"publicStudy": True}) is True
        # ...but an EXPLICIT read restriction vetoes it.
        assert (
            cbioportal.study_is_redistributable({"publicStudy": True, "readPermission": False})
            is False
        )

    def test_citations_and_scope_labels_are_present(self) -> None:
        # The attribution is a licence condition: three portal citations, verified DOIs in-source.
        assert len(cbioportal.CBIOPORTAL_CITATIONS) == 3
        assert any("Cerami" in c for c in cbioportal.CBIOPORTAL_CITATIONS)
        # The scope is stated so the number is never read as the full alteration frequency.
        assert "mutation" in cbioportal.ALTERATION_SCOPE.lower()


class TestResolveEntrez:
    @respx.mock
    async def test_maps_ensembl_to_entrez_by_id(self) -> None:
        respx.post(MYGENE).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"query": "ENSG00000157764", "entrezgene": "673", "symbol": "BRAF"},
                    {"query": "ENSG00000133703", "entrezgene": 3845, "symbol": "KRAS"},
                ],
            )
        )
        async with httpx.AsyncClient() as client:
            got = await resolve_entrez(client, ["ENSG00000157764", "ENSG00000133703"])
        assert got == {"ENSG00000157764": 673, "ENSG00000133703": 3845}

    @respx.mock
    async def test_a_gene_mygene_cannot_resolve_is_omitted_never_guessed(self) -> None:
        respx.post(MYGENE).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"query": "ENSG00000157764", "entrezgene": 673},
                    {"query": "ENSG_UNKNOWN", "notfound": True},
                ],
            )
        )
        async with httpx.AsyncClient() as client:
            got = await resolve_entrez(client, ["ENSG00000157764", "ENSG_UNKNOWN"])
        assert got == {"ENSG00000157764": 673}

    @respx.mock
    async def test_a_total_failure_returns_empty_so_every_gene_is_not_measured(self) -> None:
        respx.post(MYGENE).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            assert await resolve_entrez(client, ["ENSG00000157764"]) == {}

    async def test_no_ids_makes_no_call(self) -> None:
        async with httpx.AsyncClient() as client:
            assert await resolve_entrez(client, []) == {}
