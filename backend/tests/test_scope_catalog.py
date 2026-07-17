"""The soft-scoping pass: mark non-oncology drugs out of scope without deleting them.

Drives the real pass against a real database with ChEMBL's drug_indication mocked at
the HTTP boundary. Pins the three properties that make it safe: --dry-run writes
nothing, a real pass sets in_scope from the classifier, and a known oncology drug is
never excluded even when the rule would -- the override protects it and the run says so.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.scope_catalog import KNOWN_ONCOLOGY, scope_catalog
from backend.models import DataMaturity, Drug
from backend.repositories import DrugRepository

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
_KNOWN_ID = "CHEMBL941"  # imatinib, in KNOWN_ONCOLOGY

# molecule id -> its drug_indication rows (mesh_heading, efo_term, max_phase_for_ind)
_INDICATIONS: dict[str, list[dict[str, Any]]] = {
    "CHEMBL_ONCO": [
        {"mesh_heading": "Carcinoma, Non-Small-Cell Lung", "efo_term": None, "max_phase_for_ind": 4}
    ],
    # A statin shape: approved (phase 4), only an exploratory blunt "Neoplasms" study.
    "CHEMBL_STATIN": [{"mesh_heading": "Neoplasms", "efo_term": None, "max_phase_for_ind": 2}],
    # A known oncology drug whose mocked indications would (wrongly) trip the rule: the
    # override must keep it in scope and record the disagreement.
    _KNOWN_ID: [{"mesh_heading": "Neoplasms", "efo_term": None, "max_phase_for_ind": 1}],
}


def _handler(request: httpx.Request) -> httpx.Response:
    cid = request.url.params["molecule_chembl_id"]
    return httpx.Response(200, json={"drug_indications": _INDICATIONS.get(cid, [])})


@pytest.fixture
async def catalog(session: AsyncSession) -> None:
    """A clean three-drug catalog, so the pass's counts are exactly these rows.

    TRUNCATE because these tests assert evaluated/kept/excluded counts, and the session
    fixture only truncates at teardown -- an api-fixture test before this one would
    otherwise leave rows the pass would also score.
    """
    await session.execute(text("TRUNCATE TABLE drug CASCADE"))
    repo = DrugRepository(session)
    for cid in ("CHEMBL_ONCO", "CHEMBL_STATIN", _KNOWN_ID):
        await repo.upsert_drug(
            cid, pref_name=cid.lower(), max_phase=4, maturity=DataMaturity.PARTIAL
        )
    await session.commit()


@respx.mock
async def test_dry_run_reports_but_writes_nothing(
    session: AsyncSession, fast_client: httpx.AsyncClient, catalog: None
) -> None:
    respx.get(url__startswith=f"{CHEMBL}/drug_indication.json").mock(side_effect=_handler)

    stats = await scope_catalog(session, client=fast_client, dry_run=True)

    # It judged them -- the statin out, the oncology drug in -- but touched no row.
    assert stats.kept == 2  # ONCO (specific cancer) + the known drug (override)
    assert stats.excluded == 1  # the statin
    for cid in ("CHEMBL_ONCO", "CHEMBL_STATIN", _KNOWN_ID):
        drug = await session.get(Drug, cid)
        assert drug is not None
        await session.refresh(drug)
        assert drug.in_scope is None, f"{cid} was written despite --dry-run"


@respx.mock
async def test_applies_scope_and_the_known_override_protects(
    session: AsyncSession, fast_client: httpx.AsyncClient, catalog: None
) -> None:
    respx.get(url__startswith=f"{CHEMBL}/drug_indication.json").mock(side_effect=_handler)

    stats = await scope_catalog(session, client=fast_client)

    onco = await session.get(Drug, "CHEMBL_ONCO")
    statin = await session.get(Drug, "CHEMBL_STATIN")
    known = await session.get(Drug, _KNOWN_ID)
    assert onco is not None and statin is not None and known is not None
    for d in (onco, statin, known):
        await session.refresh(d)

    assert onco.in_scope is True  # specific malignancy -> kept
    assert statin.in_scope is False  # blunt-only, trailing phase -> excluded
    # The rule would have excluded the known drug (blunt "Neoplasms" at phase 1 < 4), but
    # the override keeps it and the run flags the disagreement rather than hiding it.
    assert known.in_scope is True
    assert KNOWN_ONCOLOGY[_KNOWN_ID] in " ".join(stats.known_wrongly_excluded)
    assert "too aggressive" in stats.report()


@respx.mock
async def test_default_pass_skips_already_scored_rows(
    session: AsyncSession, fast_client: httpx.AsyncClient, catalog: None
) -> None:
    respx.get(url__startswith=f"{CHEMBL}/drug_indication.json").mock(side_effect=_handler)

    # Pre-score one row: a resumed pass must leave it alone and judge only the NULLs.
    await DrugRepository(session).upsert_drug("CHEMBL_ONCO", in_scope=True)
    await session.commit()

    stats = await scope_catalog(session, client=fast_client)
    # Only the two still-NULL rows were evaluated; in_scope IS NULL is the bookmark.
    assert stats.evaluated == 2
