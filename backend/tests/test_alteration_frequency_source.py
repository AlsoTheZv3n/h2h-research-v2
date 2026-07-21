"""The cBioPortal alteration-frequency source (#43): its four honest states, kept distinct.

  unmapped      no cBioPortal cohort for this cancer (the dominant case) -- and NO network call
  measured      a mapped cohort, per-gene mutation frequency, with full attribution
  gene_unmapped a landscape gene we could not join to an Entrez id -- not a 0%
  source_failed an outage during the fetch -- amber "unavailable", never a zero

A green test here would prove little if it could not fail, so each state asserts the thing that
distinguishes it from the others (a pct vs a state string vs no HTTP vs SOURCE_FAILED)."""

from __future__ import annotations

from typing import Any, cast

import httpx
import respx

from backend.ingestion.base import FactStatus
from backend.ingestion.enrich_cancer import make_alteration_frequency_source
from backend.models import Cancer

OT = "https://api.platform.opentargets.org/api/v4/graphql"
MYGENE = "https://mygene.info/v3/query"
API = "https://www.cbioportal.org/api"
STUDY = "skcm_tcga_pan_can_atlas_2018"
DISEASE = "MONDO_0005012"

STUDY_MAP = {DISEASE: (STUDY, "Cutaneous Melanoma — TCGA PanCancer Atlas")}


def _cancer() -> Cancer:
    return Cancer(disease_id=DISEASE, name="cutaneous melanoma", n_drugs=0, n_targets=0)


def _landscape_genes(*pairs: tuple[str, str]) -> httpx.Response:
    rows = [
        {"score": round(0.9 - i * 0.05, 3), "target": {"id": ens, "approvedSymbol": sym}}
        for i, (ens, sym) in enumerate(pairs)
    ]
    return httpx.Response(
        200, json={"data": {"disease": {"id": DISEASE, "associatedTargets": {"rows": rows}}}}
    )


def _mygene(mapping: dict[str, int]) -> httpx.Response:
    return httpx.Response(200, json=[{"query": e, "entrezgene": g} for e, g in mapping.items()])


def _study_obj() -> dict[str, Any]:
    return {
        "studyId": STUDY,
        "name": "Skin Cutaneous Melanoma (TCGA, PanCancer Atlas)",
        "citation": "TCGA, Cell 2018",
        "pmid": "29625048",
        "publicStudy": True,
        "readPermission": True,
    }


def _mock_cbioportal(
    sequenced: int, muts: list[dict[str, Any]], *, study: dict[str, Any] | None = None
) -> None:
    respx.get(f"{API}/studies/{STUDY}").mock(
        return_value=httpx.Response(200, json=study or _study_obj())
    )
    respx.get(f"{API}/sample-lists/{STUDY}_sequenced").mock(
        return_value=httpx.Response(200, json={"sampleIds": [f"S{i}" for i in range(sequenced)]})
    )
    respx.post(f"{API}/molecular-profiles/{STUDY}_mutations/mutations/fetch").mock(
        return_value=httpx.Response(200, json=muts)
    )


class TestAlterationFrequencySource:
    @respx.mock
    async def test_a_cancer_with_no_mapped_cohort_is_unmapped_and_makes_no_call(self) -> None:
        # The dominant case (~98% of the catalog). An OK fact whose value says "unmapped", and --
        # crucially -- NOT a network call. @respx.mock with no registered route enforces it: a stray
        # request raises (assert-all-mocked), catching a regression that calls out before the check.
        source = make_alteration_frequency_source({})  # empty map -> nothing resolves
        async with httpx.AsyncClient() as client:
            record = await source(client, _cancer())
        fact = record.facts["alteration_frequency"]
        assert fact.status is FactStatus.OK
        assert fact.value == {"state": "unmapped"}

    @respx.mock
    async def test_a_mapped_cohort_measures_per_gene_frequency_with_attribution(self) -> None:
        respx.post(OT).mock(
            return_value=_landscape_genes(("ENSG00000157764", "BRAF"), ("ENSG00000213281", "NRAS"))
        )
        respx.post(MYGENE).mock(
            return_value=_mygene({"ENSG00000157764": 673, "ENSG00000213281": 4893})
        )
        # BRAF 233/440 = 53.0% (the probe truth); NRAS 125/440 = 28.4%.
        muts = [{"entrezGeneId": 673, "sampleId": f"S{i}"} for i in range(233)]
        muts += [{"entrezGeneId": 4893, "sampleId": f"S{i}"} for i in range(125)]
        _mock_cbioportal(440, muts)

        source = make_alteration_frequency_source(STUDY_MAP)
        async with httpx.AsyncClient() as client:
            record = await source(client, _cancer())

        fact = record.facts["alteration_frequency"]
        assert fact.status is FactStatus.OK
        assert fact.source == "cbioportal"
        value = cast(dict[str, Any], fact.value)
        assert value["state"] == "measured"
        assert value["study_id"] == STUDY
        assert value["denominator_n"] == 440
        assert "mutation" in value["alteration_scope"].lower()
        by_symbol = {g["symbol"]: g for g in value["genes"]}
        assert by_symbol["BRAF"]["state"] == "measured"
        assert by_symbol["BRAF"]["pct"] == 53.0
        assert by_symbol["BRAF"]["entrez_id"] == 673
        assert by_symbol["NRAS"]["pct"] == 28.4
        # The licence condition: three portal citations + the specific source study.
        assert len(value["attribution"]["portal"]) == 3
        assert value["attribution"]["study_citation"] == "TCGA, Cell 2018"
        assert value["attribution"]["study_pmid"] == "29625048"

    @respx.mock
    async def test_a_gene_that_does_not_resolve_to_entrez_is_gene_unmapped_not_zero(self) -> None:
        respx.post(OT).mock(
            return_value=_landscape_genes(("ENSG00000157764", "BRAF"), ("ENSG_MYSTERY", "MYSTERY"))
        )
        # mygene resolves only BRAF; MYSTERY is omitted -> gene_unmapped, distinct from 0%.
        respx.post(MYGENE).mock(return_value=_mygene({"ENSG00000157764": 673}))
        _mock_cbioportal(440, [{"entrezGeneId": 673, "sampleId": f"S{i}"} for i in range(233)])

        source = make_alteration_frequency_source(STUDY_MAP)
        async with httpx.AsyncClient() as client:
            record = await source(client, _cancer())

        value = cast(dict[str, Any], record.facts["alteration_frequency"].value)
        by_symbol = {g["symbol"]: g for g in value["genes"]}
        assert by_symbol["MYSTERY"]["state"] == "gene_unmapped"
        assert by_symbol["MYSTERY"]["entrez_id"] is None
        assert "pct" not in by_symbol["MYSTERY"]
        assert by_symbol["BRAF"]["state"] == "measured"

    @respx.mock
    async def test_a_profiled_gene_with_no_mutations_is_a_measured_zero(self) -> None:
        respx.post(OT).mock(
            return_value=_landscape_genes(("ENSG00000157764", "BRAF"), ("ENSG00000141510", "TP53"))
        )
        respx.post(MYGENE).mock(
            return_value=_mygene({"ENSG00000157764": 673, "ENSG00000141510": 7157})
        )
        # TP53 queried, no records -> measured 0% (whole-exome cohort profiled it).
        _mock_cbioportal(440, [{"entrezGeneId": 673, "sampleId": f"S{i}"} for i in range(233)])

        source = make_alteration_frequency_source(STUDY_MAP)
        async with httpx.AsyncClient() as client:
            record = await source(client, _cancer())

        value = cast(dict[str, Any], record.facts["alteration_frequency"].value)
        tp53 = {g["symbol"]: g for g in value["genes"]}["TP53"]
        assert tp53["state"] == "measured_zero"
        assert tp53["pct"] == 0.0
        assert tp53["altered_n"] == 0

    @respx.mock
    async def test_a_cbioportal_outage_is_source_failed_never_zero(self) -> None:
        respx.post(OT).mock(return_value=_landscape_genes(("ENSG00000157764", "BRAF")))
        respx.post(MYGENE).mock(return_value=_mygene({"ENSG00000157764": 673}))
        respx.get(f"{API}/studies/{STUDY}").mock(return_value=httpx.Response(503))

        source = make_alteration_frequency_source(STUDY_MAP)
        async with httpx.AsyncClient() as client:
            record = await source(client, _cancer())

        fact = record.facts["alteration_frequency"]
        assert fact.status is FactStatus.SOURCE_FAILED
        assert fact.value is None
        assert record.outage is True

    @respx.mock
    async def test_total_gene_resolution_failure_is_source_failed_not_a_cbioportal_outage(
        self,
    ) -> None:
        # mygene is down -> resolve_entrez returns {} -> no Entrez ids. This must be a source_failed
        # naming the GENE-ID lookup, NOT a cBioPortal outage (cBioPortal is never even called -- no
        # study route is registered, so @respx.mock would flag a stray call to it).
        respx.post(OT).mock(return_value=_landscape_genes(("ENSG00000157764", "BRAF")))
        respx.post(MYGENE).mock(return_value=httpx.Response(500))

        source = make_alteration_frequency_source(STUDY_MAP)
        async with httpx.AsyncClient() as client:
            record = await source(client, _cancer())

        fact = record.facts["alteration_frequency"]
        assert fact.status is FactStatus.SOURCE_FAILED
        assert record.outage is True
        assert "mygene" in (fact.error or "").lower()

    @respx.mock
    async def test_a_disease_ot_cannot_resolve_writes_no_fact(self) -> None:
        # A mapped study but OT returns no landscape genes: a lookup miss -> no fact (skipped),
        # never a measured "no genes altered".
        respx.post(OT).mock(return_value=httpx.Response(200, json={"data": {"disease": None}}))
        source = make_alteration_frequency_source(STUDY_MAP)
        async with httpx.AsyncClient() as client:
            record = await source(client, _cancer())
        assert "alteration_frequency" not in record.facts
        assert record.error
