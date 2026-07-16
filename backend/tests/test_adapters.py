"""Adapter unit tests, HTTP mocked.

Every test here corresponds to a defect the spike found by running against the live
APIs -- defects a code review had already missed. They are regression pins, not
coverage decoration.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from backend.ingestion import (
    USER_AGENT,
    ChEMBLAdapter,
    ClinicalTrialsAdapter,
    FactStatus,
    OpenTargetsAdapter,
    PubMedAdapter,
    build_client,
)
from backend.ingestion.chembl import pick_molecule

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
CT = "https://clinicaltrials.gov/api/v2/studies"
OT = "https://api.platform.opentargets.org/api/v4/graphql"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@pytest.fixture
async def client() -> Any:
    async with build_client(timeout=5.0, attempts=2) as c:
        yield c


# --- the sotorasib misresolution ------------------------------------------------

# Shaped after the real response: the unnamed analogue outranks the drug itself.
_SEARCH_SOTORASIB: dict[str, list[dict[str, Any]]] = {
    "molecules": [
        {
            "molecule_chembl_id": "CHEMBL5174767",
            "pref_name": None,
            "molecule_synonyms": [],
            "molecule_structures": {"canonical_smiles": "CC(C)analog"},
            "molecule_properties": {"full_mwt": "500.0"},
        },
        {
            "molecule_chembl_id": "CHEMBL4535757",
            "pref_name": "SOTORASIB",
            "molecule_synonyms": [{"molecule_synonym": "AMG-510"}],
            "molecule_structures": {"canonical_smiles": "CC1=CC=CC=C1"},
            "molecule_properties": {"full_mwt": "560.61", "alogp": "4.48"},
        },
    ]
}


class TestChEMBLResolution:
    def test_picks_the_named_molecule_not_the_top_hit(self) -> None:
        """The spike's worst defect: search ranks by structure, so [0] is an analogue."""
        mol = pick_molecule(_SEARCH_SOTORASIB["molecules"], "sotorasib")
        assert mol is not None
        assert mol["molecule_chembl_id"] == "CHEMBL4535757"

    def test_resolves_by_synonym(self) -> None:
        mol = pick_molecule(_SEARCH_SOTORASIB["molecules"], "AMG-510")
        assert mol is not None
        assert mol["molecule_chembl_id"] == "CHEMBL4535757"

    def test_no_name_match_is_unresolved_not_the_wrong_molecule(self) -> None:
        """An honest "unresolved" beats a confident wrong answer."""
        assert pick_molecule(_SEARCH_SOTORASIB["molecules"], "aspirin") is None

    @respx.mock
    async def test_unresolved_query_reports_an_error_and_no_facts(self, client: Any) -> None:
        respx.get(f"{CHEMBL}/molecule/search.json").mock(
            return_value=httpx.Response(200, json=_SEARCH_SOTORASIB)
        )
        record = await ChEMBLAdapter(client).fetch("aspirin")
        assert record.ok is False
        assert record.facts == {}
        assert "no ChEMBL molecule named" in (record.error or "")
        # The candidates it *did* see, so the operator can judge the miss.
        assert "CHEMBL4535757" in (record.error or "")


class TestChEMBLPartialFailure:
    @respx.mock
    async def test_failing_enrichment_keeps_the_resolved_molecule(self, client: Any) -> None:
        """Learning #3, the exact bug: mechanism.json 500'd and took a SMILES and 57
        IC50s with it. The molecule resolved -- that data is ours, and losing it
        under-reports coverage just as badly as inventing it would over-report."""
        respx.get(f"{CHEMBL}/molecule/search.json").mock(
            return_value=httpx.Response(200, json=_SEARCH_SOTORASIB)
        )
        respx.get(f"{CHEMBL}/activity.json").mock(
            return_value=httpx.Response(
                200, json={"page_meta": {"total_count": 57}, "activities": [{}]}
            )
        )
        respx.get(f"{CHEMBL}/mechanism.json").mock(return_value=httpx.Response(500))

        record = await ChEMBLAdapter(client).fetch("sotorasib")

        assert record.ok is True
        assert record.facts["smiles"].value == "CC1=CC=CC=C1"
        assert record.facts["n_ic50"].value == 57
        assert record.facts["mw"].value == pytest.approx(560.61)

        # The failure is reported, not swallowed -- and not as "no mechanism".
        moa = record.facts["moa"]
        assert moa.status is FactStatus.SOURCE_FAILED
        assert moa.value is None
        assert "mechanism" in (moa.error or "")

    @respx.mock
    async def test_absent_mechanism_is_empty_not_failed(self, client: Any) -> None:
        """A source that answered "no mechanism annotated" measured something."""
        respx.get(f"{CHEMBL}/molecule/search.json").mock(
            return_value=httpx.Response(200, json=_SEARCH_SOTORASIB)
        )
        respx.get(f"{CHEMBL}/activity.json").mock(
            return_value=httpx.Response(
                200, json={"page_meta": {"total_count": 0}, "activities": []}
            )
        )
        respx.get(f"{CHEMBL}/mechanism.json").mock(
            return_value=httpx.Response(200, json={"mechanisms": []})
        )

        record = await ChEMBLAdapter(client).fetch("sotorasib")

        assert record.facts["moa"].status is FactStatus.EMPTY
        assert record.facts["n_ic50"].status is FactStatus.EMPTY
        assert record.facts["n_ic50"].value == 0

    @respx.mock
    async def test_a_biologic_without_a_structure_still_resolves(self, client: Any) -> None:
        """Shaped after the live response for trastuzumab deruxtecan (CHEMBL4297844).

        ChEMBL knows the ADC -- name, phase 4, mechanism -- and simply has no SMILES
        for it, because it is a biologic. `ok` must mean "resolved", not "has a
        structure": marking it not-ok drops it from the catalog that §8 wants it in,
        honestly labelled. The missing structure is maturity's job to report.
        """
        respx.get(f"{CHEMBL}/molecule/search.json").mock(
            return_value=httpx.Response(
                200,
                json={
                    "molecules": [
                        {
                            "molecule_chembl_id": "CHEMBL4297844",
                            "pref_name": "TRASTUZUMAB DERUXTECAN",
                            "molecule_synonyms": [],
                            "molecule_structures": None,
                            "molecule_properties": None,
                            "max_phase": "4",
                        }
                    ]
                },
            )
        )
        respx.get(f"{CHEMBL}/activity.json").mock(
            return_value=httpx.Response(
                200, json={"page_meta": {"total_count": 0}, "activities": []}
            )
        )
        respx.get(f"{CHEMBL}/mechanism.json").mock(
            return_value=httpx.Response(
                200,
                json={
                    "mechanisms": [
                        {
                            "mechanism_of_action": "Receptor protein-tyrosine kinase erbB-2"
                            " binding agent",
                            "action_type": "BINDING AGENT",
                            "target_chembl_id": "CHEMBL1824",
                        }
                    ]
                },
            )
        )

        record = await ChEMBLAdapter(client).fetch("trastuzumab deruxtecan")

        assert record.ok is True
        assert record.facts["chembl_id"].value == "CHEMBL4297844"
        assert record.facts["max_phase"].value == 4
        assert str(record.facts["moa"].value).startswith("Receptor protein-tyrosine kinase")
        # No structure -- measured and absent, not a failure to measure.
        assert record.facts["smiles"].status is FactStatus.EMPTY
        assert record.facts["smiles"].value is None

    @respx.mock
    async def test_search_failure_is_hard(self, client: Any) -> None:
        """No molecule means no facts: there is nothing to be partial about."""
        respx.get(f"{CHEMBL}/molecule/search.json").mock(return_value=httpx.Response(500))
        record = await ChEMBLAdapter(client).fetch("sotorasib")
        assert record.ok is False
        assert record.facts == {}
        assert "500" in (record.error or "")

    @respx.mock
    async def test_ic50_count_comes_from_page_meta_not_page_length(self, client: Any) -> None:
        """len(page) saturates at `limit`: osimertinib showed 100 against a true 701."""
        respx.get(f"{CHEMBL}/molecule/search.json").mock(
            return_value=httpx.Response(200, json=_SEARCH_SOTORASIB)
        )
        respx.get(f"{CHEMBL}/activity.json").mock(
            return_value=httpx.Response(
                200, json={"page_meta": {"total_count": 701}, "activities": [{}] * 100}
            )
        )
        respx.get(f"{CHEMBL}/mechanism.json").mock(
            return_value=httpx.Response(200, json={"mechanisms": []})
        )
        record = await ChEMBLAdapter(client).fetch("sotorasib")
        assert record.facts["n_ic50"].value == 701
        assert record.facts["n_ic50_scanned"].value == 100


class TestClinicalTrials:
    @respx.mock
    async def test_count_comes_from_total_not_page(self, client: Any) -> None:
        route = respx.get(CT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "totalCount": 383,
                    "studies": [
                        {
                            "protocolSection": {
                                "designModule": {"phases": ["PHASE4", "PHASE1"]},
                                "statusModule": {"overallStatus": "COMPLETED"},
                            }
                        }
                    ]
                    * 100,
                },
            )
        )
        record = await ClinicalTrialsAdapter(client).fetch("osimertinib")
        assert record.facts["n_trials"].value == 383
        assert record.facts["n_trials_scanned"].value == 100
        assert record.facts["ct_max_phase"].value == 4
        assert route.calls.last.request.url.params["countTotal"] == "true"

    @respx.mock
    async def test_sends_a_user_agent_the_waf_accepts(self, client: Any) -> None:
        """CT.gov 403s unknown UAs. Measured: the token is what gets us through, and
        a hardcoded version would rot silently into a 403 on the next httpx bump."""
        route = respx.get(CT).mock(
            return_value=httpx.Response(200, json={"totalCount": 0, "studies": []})
        )
        await ClinicalTrialsAdapter(client).fetch("sotorasib")
        ua = route.calls.last.request.headers["user-agent"]
        assert ua == USER_AGENT
        assert ua.startswith(f"python-httpx/{httpx.__version__}")
        assert "h2h" in ua

    @respx.mock
    async def test_zero_trials_is_empty_not_failed(self, client: Any) -> None:
        respx.get(CT).mock(return_value=httpx.Response(200, json={"totalCount": 0, "studies": []}))
        record = await ClinicalTrialsAdapter(client).fetch("nonexistent")
        assert record.facts["n_trials"].status is FactStatus.EMPTY
        assert record.facts["n_trials"].value == 0

    @respx.mock
    async def test_a_403_is_not_retried(self, client: Any) -> None:
        """The WAF's 403 is a verdict, not a blip. Retrying only delays the truth."""
        route = respx.get(CT).mock(return_value=httpx.Response(403))
        record = await ClinicalTrialsAdapter(client).fetch("sotorasib")
        assert route.call_count == 1
        assert record.ok is False
        assert "403" in (record.error or "")

    @respx.mock
    async def test_a_500_is_retried(self, client: Any) -> None:
        route = respx.route(method="GET", url=CT).mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(200, json={"totalCount": 7, "studies": []}),
            ]
        )
        record = await ClinicalTrialsAdapter(client).fetch("sotorasib")
        assert route.call_count == 2
        assert record.facts["n_trials"].value == 7


class TestOpenTargets:
    @staticmethod
    def _drug_payload() -> dict[str, Any]:
        return {
            "data": {
                "drug": {
                    "id": "CHEMBL1200609",
                    "name": "TRASTUZUMAB DERUXTECAN",
                    "drugType": "Antibody drug conjugate",
                    "maximumClinicalStage": "APPROVAL",
                    "mechanismsOfAction": {
                        "rows": [
                            {
                                "mechanismOfAction": "ERBB2 binding agent",
                                "actionType": "BINDING AGENT",
                                "targets": [{"approvedSymbol": "ERBB2"}],
                            },
                            {
                                "mechanismOfAction": "TOP1 inhibitor",
                                "actionType": "INHIBITOR",
                                "targets": [{"approvedSymbol": "TOP1"}],
                            },
                        ]
                    },
                    "indications": {
                        "count": 34,
                        "rows": [{"disease": {"name": "breast carcinoma"}}],
                    },
                }
            }
        }

    @respx.mock
    async def test_keeps_every_mechanism(self, client: Any) -> None:
        """The ADC has two genuinely distinct mechanisms; rows[0] halves the answer."""
        respx.post(OT).mock(
            side_effect=[
                httpx.Response(200, json={"data": {"search": {"hits": [{"id": "CHEMBL1200609"}]}}}),
                httpx.Response(200, json=self._drug_payload()),
            ]
        )
        record = await OpenTargetsAdapter(client).fetch("trastuzumab deruxtecan")
        assert record.facts["all_moas"].value == ["ERBB2 binding agent", "TOP1 inhibitor"]
        assert record.facts["targets"].value == ["ERBB2", "TOP1"]
        # The column that makes the ADC honest in the overview.
        assert record.facts["drug_type"].value == "Antibody drug conjugate"
        assert record.facts["max_stage"].value == "APPROVAL"

    @respx.mock
    async def test_graphql_errors_are_surfaced_verbatim(self, client: Any) -> None:
        """A 200 carrying an errors array is the silent case: without this the fields
        come back null with no error, which reads as "the source has no data"."""
        respx.post(OT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [
                        {
                            "message": "Cannot query field 'maximumClinicalTrialPhase' on type"
                            " 'Drug'. Did you mean 'maximumClinicalStage'?"
                        }
                    ]
                },
            )
        )
        record = await OpenTargetsAdapter(client).fetch("sotorasib")
        assert record.ok is False
        # The server names the new field. That message is the whole value of drift detection.
        assert "maximumClinicalStage" in (record.error or "")

    @respx.mock
    async def test_non_json_error_stays_legible(self, client: Any) -> None:
        respx.post(OT).mock(return_value=httpx.Response(502, html="<html>bad gateway</html>"))
        record = await OpenTargetsAdapter(client).fetch("sotorasib")
        assert record.ok is False
        assert "502" in (record.error or "")


class TestPubMed:
    @respx.mock
    async def test_count_and_titles(self, client: Any) -> None:
        respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(
                200, json={"esearchresult": {"count": "654", "idlist": ["1", "2"]}}
            )
        )
        respx.get(f"{EUTILS}/esummary.fcgi").mock(
            return_value=httpx.Response(
                200,
                json={
                    "result": {
                        "uids": ["1", "2"],
                        "1": {"title": "Sotorasib."},
                        "2": {"title": "KRAS."},
                    }
                },
            )
        )
        record = await PubMedAdapter(client).fetch("sotorasib")
        assert record.facts["n_pubmed"].value == 654
        assert record.facts["sample_titles"].value == ["Sotorasib.", "KRAS."]

    @respx.mock
    async def test_a_failing_summary_keeps_the_count(self, client: Any) -> None:
        """Titles are a garnish on the count; losing them must not lose the count."""
        respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(
                200, json={"esearchresult": {"count": "654", "idlist": ["1"]}}
            )
        )
        respx.get(f"{EUTILS}/esummary.fcgi").mock(return_value=httpx.Response(500))
        record = await PubMedAdapter(client).fetch("sotorasib")
        assert record.facts["n_pubmed"].value == 654
        assert record.facts["sample_titles"].status is FactStatus.SOURCE_FAILED

    @respx.mock
    async def test_api_key_is_sent_only_when_configured(self, client: Any) -> None:
        route = respx.get(f"{EUTILS}/esearch.fcgi").mock(
            return_value=httpx.Response(200, json={"esearchresult": {"count": "1", "idlist": []}})
        )
        await PubMedAdapter(client, api_key=None).fetch("x")
        assert "api_key" not in route.calls.last.request.url.params

        await PubMedAdapter(client, api_key="secret").fetch("x")
        assert route.calls.last.request.url.params["api_key"] == "secret"
