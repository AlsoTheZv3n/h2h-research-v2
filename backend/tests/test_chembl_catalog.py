"""Bulk-loader behaviour, HTTP mocked.

The loader's hard requirement is not speed, it is honesty under a flaky source:
re-runnable without duplicating, gap-filling, and never reporting a partial load
as a complete catalog.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.chembl_catalog import (
    LoadStats,
    is_cancer_indication,
    load_catalog,
    to_columns,
)
from backend.models import DataMaturity, Drug

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"


class TestCancerFilter:
    @pytest.mark.parametrize(
        "row",
        [
            {"mesh_heading": "Breast Neoplasms", "efo_term": None},
            {"mesh_heading": "Carcinoma, Non-Small-Cell Lung", "efo_term": None},
            {"mesh_heading": None, "efo_term": "prostate carcinoma"},
            {"mesh_heading": "Multiple Myeloma", "efo_term": None},
            {"mesh_heading": "Leukemia, Myeloid, Acute", "efo_term": None},
        ],
    )
    def test_cancer_rows_match(self, row: dict[str, Any]) -> None:
        """MeSH names organ cancers '<Organ> Neoplasms' but others 'Carcinoma, ...',
        so matching one field or one term would miss half the catalog."""
        assert is_cancer_indication(row) is True

    @pytest.mark.parametrize(
        "row",
        [
            {"mesh_heading": "Hypertension", "efo_term": None},
            {"mesh_heading": "Diabetes Mellitus, Type 2", "efo_term": "diabetes mellitus"},
            {"mesh_heading": None, "efo_term": None},
        ],
    )
    def test_non_cancer_rows_do_not_match(self, row: dict[str, Any]) -> None:
        assert is_cancer_indication(row) is False


class TestColumnMapping:
    def test_biologic_without_structure_is_index_only(self) -> None:
        """The ADC belongs in the catalog, labelled honestly -- not excluded."""
        columns = to_columns(
            {
                "molecule_chembl_id": "CHEMBL4297844",
                "pref_name": "TRASTUZUMAB DERUXTECAN",
                "molecule_type": "Antibody",
                "max_phase": "4",
                "molecule_structures": None,
                "molecule_properties": None,
            }
        )
        assert columns["maturity"] is DataMaturity.INDEX_ONLY
        assert columns["smiles"] is None
        assert columns["max_phase"] == 4

    def test_chembl_string_decimals_are_coerced(self) -> None:
        """ChEMBL serializes decimals as strings; the column is a float."""
        columns = to_columns(
            {
                "molecule_chembl_id": "CHEMBL4594350",
                "pref_name": "ADAGRASIB",
                "molecule_type": "Small molecule",
                "max_phase": "4",
                "molecule_structures": {"canonical_smiles": "CCO"},
                "molecule_properties": {"full_mwt": "604.13", "alogp": "4.73"},
            }
        )
        assert columns["mw"] == pytest.approx(604.13)
        assert columns["alogp"] == pytest.approx(4.73)


def _indication_page(rows: list[dict[str, Any]], nxt: str | None = None) -> dict[str, Any]:
    return {"drug_indications": rows, "page_meta": {"next": nxt, "total_count": len(rows)}}


def _mock_discovery(rows: list[dict[str, Any]]) -> None:
    """Every discovery query answers with the same one page."""
    respx.get(url__startswith=f"{CHEMBL}/drug_indication.json").mock(
        return_value=httpx.Response(200, json=_indication_page(rows))
    )


_ADAGRASIB = {
    "molecule_chembl_id": "CHEMBL4594350",
    "pref_name": "ADAGRASIB",
    "molecule_type": "Small molecule",
    "max_phase": "4",
    "molecule_structures": {"canonical_smiles": "CCO"},
    "molecule_properties": {"full_mwt": "604.13"},
}


class TestLoad:
    @respx.mock
    async def test_loads_cancer_drugs_and_skips_the_rest(
        self, session: AsyncSession, fast_client: httpx.AsyncClient
    ) -> None:
        _mock_discovery(
            [
                {
                    "molecule_chembl_id": "CHEMBL4594350",
                    "mesh_heading": "Carcinoma, Non-Small-Cell Lung",
                    "max_phase_for_ind": "4",
                },
                {
                    "molecule_chembl_id": "CHEMBL_ASPIRIN",
                    "mesh_heading": "Headache",
                    "max_phase_for_ind": "4",
                },
            ]
        )
        respx.get(url__startswith=f"{CHEMBL}/molecule.json").mock(
            return_value=httpx.Response(200, json={"molecules": [_ADAGRASIB]})
        )

        stats = await load_catalog(session, client=fast_client)

        assert stats.loaded == 1
        drug = await session.get(Drug, "CHEMBL4594350")
        assert drug is not None
        assert drug.pref_name == "ADAGRASIB"
        assert await session.get(Drug, "CHEMBL_ASPIRIN") is None

    @respx.mock
    async def test_preclinical_is_skipped(
        self, session: AsyncSession, fast_client: httpx.AsyncClient
    ) -> None:
        """max_phase >= 1: a compound that never reached a patient is another product."""
        _mock_discovery(
            [
                {
                    "molecule_chembl_id": "CHEMBL_PRECLIN",
                    "mesh_heading": "Breast Neoplasms",
                    "max_phase_for_ind": "0",
                }
            ]
        )
        stats = await load_catalog(session, client=fast_client)
        assert stats.loaded == 0
        assert stats.skipped_phase == 1

    @respx.mock
    async def test_rerunning_does_not_duplicate(
        self, session: AsyncSession, fast_client: httpx.AsyncClient
    ) -> None:
        """The whole point of upserts: re-run after an outage without a mess."""
        _mock_discovery(
            [
                {
                    "molecule_chembl_id": "CHEMBL4594350",
                    "mesh_heading": "Breast Neoplasms",
                    "max_phase_for_ind": "4",
                }
            ]
        )
        respx.get(url__startswith=f"{CHEMBL}/molecule.json").mock(
            return_value=httpx.Response(200, json={"molecules": [_ADAGRASIB]})
        )

        await load_catalog(session, client=fast_client)
        await load_catalog(session, client=fast_client)

        count = await session.scalar(select(func.count()).select_from(Drug))
        assert count == 1

    @respx.mock
    async def test_a_failed_batch_falls_back_to_single_fetches(
        self, session: AsyncSession, fast_client: httpx.AsyncClient
    ) -> None:
        """One bad record must not cost us the other 19 in its batch."""
        _mock_discovery(
            [
                {
                    "molecule_chembl_id": "CHEMBL4594350",
                    "mesh_heading": "Breast Neoplasms",
                    "max_phase_for_ind": "4",
                },
                {
                    "molecule_chembl_id": "CHEMBL_BROKEN",
                    "mesh_heading": "Breast Neoplasms",
                    "max_phase_for_ind": "4",
                },
            ]
        )
        respx.get(url__startswith=f"{CHEMBL}/molecule.json").mock(return_value=httpx.Response(500))
        respx.get(f"{CHEMBL}/molecule/CHEMBL4594350.json").mock(
            return_value=httpx.Response(200, json=_ADAGRASIB)
        )
        respx.get(f"{CHEMBL}/molecule/CHEMBL_BROKEN.json").mock(return_value=httpx.Response(500))

        stats = await load_catalog(session, client=fast_client)

        assert stats.loaded == 1
        assert stats.failed == ["CHEMBL_BROKEN"]
        assert await session.get(Drug, "CHEMBL4594350") is not None

    @respx.mock
    async def test_only_missing_skips_what_we_have(
        self, session: AsyncSession, fast_client: httpx.AsyncClient
    ) -> None:
        _mock_discovery(
            [
                {
                    "molecule_chembl_id": "CHEMBL4594350",
                    "mesh_heading": "Breast Neoplasms",
                    "max_phase_for_ind": "4",
                }
            ]
        )
        route = respx.get(url__startswith=f"{CHEMBL}/molecule.json").mock(
            return_value=httpx.Response(200, json={"molecules": [_ADAGRASIB]})
        )
        await load_catalog(session, client=fast_client)
        calls_after_first = route.call_count

        await load_catalog(session, client=fast_client, only_missing=True)
        assert route.call_count == calls_after_first  # nothing left to fetch

    @respx.mock
    async def test_a_lost_discovery_page_is_reported_not_swallowed(
        self, session: AsyncSession, fast_client: httpx.AsyncClient
    ) -> None:
        """A partial load must never read as the catalog size.

        This is the spike's lesson at the command level: the number this prints is
        the number the "1000+ vs 20" decision rests on, and an outage silently
        halving it would be the same lie in a new place.
        """
        respx.get(url__startswith=f"{CHEMBL}/drug_indication.json").mock(
            return_value=httpx.Response(500)
        )
        stats = await load_catalog(session, client=fast_client)

        assert stats.pages_failed > 0
        assert "FLOOR" in stats.report()
        assert "incomplete" in stats.report()


class TestStatsReport:
    def test_a_clean_run_does_not_cry_wolf(self) -> None:
        stats = LoadStats(indications_scanned=10, candidates=5, loaded=5)
        assert "FLOOR" not in stats.report()
