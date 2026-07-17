"""The pre-warmer fills unenriched drugs and skips what is already done.

The whole dedup + resumability story is one filter -- last_enriched_at IS NULL -- so
this test guards exactly that: an already-enriched drug is never touched again, and a
never-enriched one is. If the filter regresses, the pre-warmer starts redoing the
whole catalog on every pass, which is both wasteful and a way to hammer ChEMBL.
"""

from __future__ import annotations

import httpx
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import SourceRecord, fact, utcnow
from backend.ingestion.enrich import enrich_catalog
from backend.models import Drug
from backend.repositories import DrugRepository

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
CT = "https://clinicaltrials.gov/api/v2/studies"
OT = "https://api.platform.opentargets.org/api/v4/graphql"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _mock_sources(cid: str) -> None:
    respx.get(f"{CHEMBL}/molecule/search.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "molecules": [
                    {
                        "molecule_chembl_id": cid,
                        "pref_name": "WARMDRUG",
                        "molecule_synonyms": [],
                        "molecule_structures": {"canonical_smiles": "CCO"},
                        "molecule_properties": {"full_mwt": "100.0"},
                        "max_phase": "4",
                    }
                ]
            },
        )
    )
    respx.get(f"{CHEMBL}/mechanism.json").mock(
        return_value=httpx.Response(200, json={"mechanisms": []})
    )
    respx.get(f"{CHEMBL}/activity.json").mock(
        return_value=httpx.Response(200, json={"page_meta": {"total_count": 0}, "activities": []})
    )
    respx.get(CT).mock(return_value=httpx.Response(200, json={"totalCount": 0, "studies": []}))
    respx.post(OT).mock(return_value=httpx.Response(200, json={"data": {"search": {"hits": []}}}))
    respx.get(f"{EUTILS}/esearch.fcgi").mock(
        return_value=httpx.Response(200, json={"esearchresult": {"count": "0", "idlist": []}})
    )
    respx.get(f"{EUTILS}/efetch.fcgi").mock(
        return_value=httpx.Response(200, text="<PubmedArticleSet></PubmedArticleSet>")
    )


@respx.mock
async def test_the_prewarmer_skips_already_enriched_and_fills_the_rest(
    session: AsyncSession,
) -> None:
    repo = DrugRepository(session)

    # Already enriched: last_enriched_at set, a real fact. Must be left untouched.
    stamped = utcnow()
    await repo.upsert_drug("CHEMBL_DONE", pref_name="donedrug", last_enriched_at=stamped)
    await repo.save_record(
        "CHEMBL_DONE",
        SourceRecord("chembl", "donedrug", ok=True, facts={"smiles": fact("CCO", "chembl")}),
    )
    # Never enriched: the drug the pre-warmer exists to fill.
    await repo.upsert_drug("CHEMBL_WARM", pref_name="WARMDRUG", max_phase=4)
    await session.commit()

    _mock_sources("CHEMBL_WARM")
    stats = await enrich_catalog(session, only_unenriched=True)

    # Exactly one drug was loaded and processed -- the unenriched one. This count IS
    # the proof the filter worked: the already-enriched drug never entered the batch.
    assert stats.drugs == 1

    warm = await session.get(Drug, "CHEMBL_WARM")
    assert warm is not None and warm.last_enriched_at is not None, "the unenriched drug was skipped"

    done = await session.get(Drug, "CHEMBL_DONE")
    assert done is not None
    # Its stamp is exactly what it was: the pre-warmer never re-enriched it.
    assert done.last_enriched_at == stamped


@respx.mock
async def test_without_the_filter_both_drugs_are_processed(session: AsyncSession) -> None:
    """The contrast that proves the filter is load-bearing, not decoration: drop it
    and the already-enriched drug is picked up again."""
    repo = DrugRepository(session)
    await repo.upsert_drug("CHEMBL_DONE", pref_name="WARMDRUG", last_enriched_at=utcnow())
    await repo.upsert_drug("CHEMBL_WARM", pref_name="WARMDRUG", max_phase=4)
    await session.commit()

    _mock_sources("CHEMBL_WARM")
    stats = await enrich_catalog(session, only_unenriched=False)

    assert stats.drugs == 2
