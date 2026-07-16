"""The enrichment step: the path that actually runs the adapters and writes facts.

This test exists because its absence hid the largest defect in Phase 1. The adapters
were ported, unit-tested and correct -- and nothing outside the test suite ever
called them. The catalog held index columns, the fact table was populated only by
tests, and `GET /drugs/{id}` would have answered `facts: {}, unavailable: []` for
every drug in a real deployment: a positive assertion that no source had failed.

So this drives the real entrypoint end to end and asserts the API serves what it
produced.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.chembl_catalog import to_columns
from backend.ingestion.enrich import enrich_catalog
from backend.models import DataMaturity, Drug
from backend.repositories import DrugRepository

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
CT = "https://clinicaltrials.gov/api/v2/studies"
OT = "https://api.platform.opentargets.org/api/v4/graphql"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

KRAS_TARGET = "CHEMBL2189121"


def _mock_all_sources(*, chembl_ok: bool = True) -> None:
    respx.get(f"{CHEMBL}/molecule/search.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "molecules": [
                    {
                        "molecule_chembl_id": "CHEMBL4594350",
                        "pref_name": "ADAGRASIB",
                        "molecule_synonyms": [],
                        "molecule_structures": {"canonical_smiles": "CCO"},
                        "molecule_properties": {"full_mwt": "604.13", "num_ro5_violations": "0"},
                        "max_phase": "4",
                    }
                ]
            },
        )
    )
    respx.get(f"{CHEMBL}/mechanism.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "mechanisms": [
                    {
                        "mechanism_of_action": "GTPase KRas inhibitor",
                        "action_type": "INHIBITOR",
                        "target_chembl_id": KRAS_TARGET,
                    }
                ]
            },
        )
    )
    respx.get(f"{CHEMBL}/activity.json").mock(
        return_value=httpx.Response(200, json={"page_meta": {"total_count": 30}, "activities": []})
        if not chembl_ok
        else httpx.Response(
            200,
            json={
                "page_meta": {"total_count": 2},
                "activities": [
                    {
                        "target_chembl_id": KRAS_TARGET,
                        "target_pref_name": "GTPase KRas",
                        "standard_value": "10",
                        "standard_relation": "=",
                        "standard_units": "nM",
                    },
                    {
                        "target_chembl_id": "CHEMBL4303835",
                        "target_pref_name": "SARS-CoV-2",
                        "standard_value": "45000",
                        "standard_relation": "=",
                        "standard_units": "nM",
                    },
                ],
            },
        )
    )
    respx.get(CT).mock(
        return_value=httpx.Response(
            200,
            json={
                "totalCount": 39,
                "studies": [
                    {
                        "protocolSection": {
                            "designModule": {"phases": ["PHASE3"]},
                            "statusModule": {"overallStatus": "COMPLETED"},
                        }
                    }
                ],
            },
        )
    )
    respx.post(OT).mock(
        side_effect=[
            httpx.Response(200, json={"data": {"search": {"hits": [{"id": "CHEMBL4594350"}]}}}),
            httpx.Response(
                200,
                json={
                    "data": {
                        "drug": {
                            "id": "CHEMBL4594350",
                            "drugType": "Small molecule",
                            "maximumClinicalStage": "APPROVAL",
                            "mechanismsOfAction": {
                                "rows": [
                                    {
                                        "mechanismOfAction": "GTPase KRas inhibitor",
                                        "actionType": "INHIBITOR",
                                        "targets": [{"approvedSymbol": "KRAS"}],
                                    }
                                ]
                            },
                            "indications": {
                                "count": 9,
                                "rows": [{"disease": {"name": "lung carcinoma"}}],
                            },
                        }
                    }
                },
            ),
        ]
    )
    respx.get(f"{EUTILS}/esearch.fcgi").mock(
        return_value=httpx.Response(200, json={"esearchresult": {"count": "354", "idlist": ["1"]}})
    )
    respx.get(f"{EUTILS}/esummary.fcgi").mock(
        return_value=httpx.Response(
            200, json={"result": {"uids": ["1"], "1": {"title": "Adagrasib."}}}
        )
    )


@pytest.fixture
async def catalogued(session: AsyncSession) -> None:
    """A catalog row as the bulk loader would leave it: index columns, no facts."""
    repo = DrugRepository(session)
    await repo.upsert_drug(
        "CHEMBL4594350",
        **to_columns(
            {
                "molecule_chembl_id": "CHEMBL4594350",
                "pref_name": "ADAGRASIB",
                "molecule_type": "Small molecule",
                "max_phase": "4",
                "molecule_structures": {"canonical_smiles": "CCO"},
                "molecule_properties": {"full_mwt": "604.13"},
            }
        ),
    )
    await session.commit()


class TestEnrichment:
    @respx.mock
    async def test_it_actually_writes_facts(
        self, session: AsyncSession, fast_client: httpx.AsyncClient, catalogued: None
    ) -> None:
        """The gap that existed: a catalogued drug had no facts, from any source."""
        _mock_all_sources()
        repo = DrugRepository(session)

        assert list(await repo.facts_for("CHEMBL4594350")) == []

        stats = await enrich_catalog(session, client=fast_client)

        assert stats.enriched == 1
        rows = await repo.facts_for("CHEMBL4594350")
        assert rows, "enrichment produced no facts at all"
        assert {r.source for r in rows} == {"chembl", "clinicaltrials", "opentargets", "pubmed"}

    @respx.mock
    async def test_every_fact_carries_provenance(
        self, session: AsyncSession, fast_client: httpx.AsyncClient, catalogued: None
    ) -> None:
        """CC BY-SA needs attribution, so this is a licensing requirement too."""
        _mock_all_sources()
        await enrich_catalog(session, client=fast_client)

        rows = await DrugRepository(session).facts_for("CHEMBL4594350")
        for row in rows:
            assert row.retrieved_at is not None, f"{row.key} has no retrieved_at"
            assert row.source_url, f"{row.key} has no source_url"

    @respx.mock
    async def test_the_overview_columns_get_populated(
        self, session: AsyncSession, fast_client: httpx.AsyncClient, catalogued: None
    ) -> None:
        """primary_target drives the overview's ?target= filter. The loader never set
        it, so the filter matched nothing -- for every drug in the catalog."""
        _mock_all_sources()
        await enrich_catalog(session, client=fast_client)

        drug = await session.get(Drug, "CHEMBL4594350")
        assert drug is not None
        await session.refresh(drug)
        assert drug.primary_target == "KRAS"
        assert drug.primary_indication == "lung carcinoma"
        assert drug.drug_type == "Small molecule"

    @respx.mock
    async def test_maturity_reaches_full_once_potency_is_known(
        self, session: AsyncSession, fast_client: httpx.AsyncClient, catalogued: None
    ) -> None:
        """The loader can only ever say has_potency=False, so nothing reached FULL
        until this step ran."""
        _mock_all_sources()
        drug = await session.get(Drug, "CHEMBL4594350")
        assert drug is not None
        before = drug.maturity  # structure, but the loader cannot know about potency

        await enrich_catalog(session, client=fast_client)
        await session.refresh(drug)
        after = drug.maturity

        assert before is DataMaturity.PARTIAL
        assert after is DataMaturity.FULL

    @respx.mock
    async def test_the_potency_summary_lands_as_a_fact(
        self, session: AsyncSession, fast_client: httpx.AsyncClient, catalogued: None
    ) -> None:
        """T5's domain logic reaching the database -- via the real entrypoint."""
        _mock_all_sources()
        await enrich_catalog(session, client=fast_client)

        rows = {
            (r.key, r.source): r for r in await DrugRepository(session).facts_for("CHEMBL4594350")
        }
        summary: Any = rows[("ic50_summary", "chembl")].value
        assert summary["median_nm"] == 10.0
        assert summary["off_target"] == {"SARS-CoV-2": 1}

    @respx.mock
    async def test_one_dead_source_does_not_stop_the_others(
        self, session: AsyncSession, fast_client: httpx.AsyncClient, catalogued: None
    ) -> None:
        """ChEMBL is down about as often as it is up. The rest of the brief must
        still be built, and the failure must be visible rather than absent."""
        _mock_all_sources()
        respx.get(f"{CHEMBL}/molecule/search.json").mock(return_value=httpx.Response(500))

        stats = await enrich_catalog(session, client=fast_client)

        assert stats.records_failed == 1
        assert stats.drugs_with_a_failure == ["CHEMBL4594350"]
        rows = await DrugRepository(session).facts_for("CHEMBL4594350")
        assert {r.source for r in rows} == {"clinicaltrials", "opentargets", "pubmed"}

    @respx.mock
    async def test_rerunning_refreshes_rather_than_duplicates(
        self, session: AsyncSession, fast_client: httpx.AsyncClient, catalogued: None
    ) -> None:
        _mock_all_sources()
        await enrich_catalog(session, client=fast_client)
        before = len(await DrugRepository(session).facts_for("CHEMBL4594350"))

        _mock_all_sources()
        await enrich_catalog(session, client=fast_client)
        after = len(await DrugRepository(session).facts_for("CHEMBL4594350"))

        assert before == after

    @respx.mock
    async def test_measured_zeros_reach_the_catalog(
        self, session: AsyncSession, fast_client: httpx.AsyncClient, catalogued: None
    ) -> None:
        """ro5_violations=0 is the best possible value, and `fact()` classifies it
        EMPTY. Promoting only OK facts dropped it to NULL -- "not measured". None !=
        0, running backwards."""
        _mock_all_sources()
        await enrich_catalog(session, client=fast_client)

        drug = await session.get(Drug, "CHEMBL4594350")
        assert drug is not None
        await session.refresh(drug)
        assert drug.ro5_violations == 0, "a measured zero was stored as 'not measured'"
