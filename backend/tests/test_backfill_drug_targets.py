"""The drug_target backfill: populate the drug->target relation for drugs enriched before it.

Drives the real backfill against a real database with Open Targets mocked at the HTTP
boundary, and pins the honest-states invariants: the target_ids fact is the "done" marker,
an EMPTY result marks a drug done (no drug_target rows, not retried forever), and a
SOURCE_FAILED target_ids -- a prior OT outage -- is NOT done, so the drug is retried once OT
is healthy rather than stranded with no catalog links.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.backfill_drug_targets import backfill
from backend.ingestion.base import FactStatus, SourceRecord, fact, failed, utcnow
from backend.models import DataMaturity
from backend.repositories import DrugRepository
from backend.repositories.cancers import CancerRepository

OT = "https://api.platform.opentargets.org/api/v4/graphql"

# name (as fetched, lowercased) -> Open Targets drug id
_NAME_TO_ID = {"hasdrug": "CHEMBL_HAS", "notgt": "CHEMBL_NOTGT", "faildrug": "CHEMBL_FAILED"}
# drug id -> the MoA targets, each with its Ensembl id. NOTGT annotates no target at all.
_TARGETS: dict[str, list[dict[str, object]]] = {
    "CHEMBL_HAS": [{"id": "ENSG_HAS", "approvedSymbol": "SYM", "targetClass": []}],
    "CHEMBL_FAILED": [{"id": "ENSG_FAIL", "approvedSymbol": "SYF", "targetClass": []}],
    "CHEMBL_NOTGT": [],
}


def _ot_handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    variables = body["variables"]
    if "search(" in body["query"]:
        drug_id = _NAME_TO_ID.get(variables["q"].lower())
        hits = [{"id": drug_id}] if drug_id else []
        return httpx.Response(200, json={"data": {"search": {"hits": hits}}})
    drug_id = variables["id"]
    return httpx.Response(
        200,
        json={
            "data": {
                "drug": {
                    "id": drug_id,
                    "drugType": "Small molecule",
                    "maximumClinicalStage": "APPROVAL",
                    "mechanismsOfAction": {
                        "rows": [
                            {
                                "mechanismOfAction": "x inhibitor",
                                "actionType": "INHIBITOR",
                                "targets": _TARGETS[drug_id],
                            }
                        ]
                    },
                    "indications": {"count": 0, "rows": []},
                }
            }
        },
    )


@pytest.fixture
async def seeded(session: AsyncSession) -> None:
    """Four enriched drugs, one per state the backfill must distinguish. TRUNCATE first so
    the candidate counts are exact (see test_backfill_target_class for the same reasoning)."""
    await session.execute(text("TRUNCATE TABLE drug CASCADE"))
    repo = DrugRepository(session)
    now = utcnow()
    # No target_ids fact yet -> a candidate; OT annotates a target -> drug_target filled.
    await repo.upsert_drug(
        "CHEMBL_HAS", pref_name="hasdrug", maturity=DataMaturity.PARTIAL, last_enriched_at=now
    )
    # No target_ids fact; OT annotates NO target -> an EMPTY fact marks it done, no rows.
    await repo.upsert_drug(
        "CHEMBL_NOTGT", pref_name="notgt", maturity=DataMaturity.PARTIAL, last_enriched_at=now
    )
    # A SOURCE_FAILED target_ids fact from a prior OT outage: "we could not look", NOT done.
    # It must be re-selected and, on the retry, actually filled.
    await repo.upsert_drug(
        "CHEMBL_FAILED", pref_name="faildrug", maturity=DataMaturity.PARTIAL, last_enriched_at=now
    )
    await repo.save_record(
        "CHEMBL_FAILED",
        SourceRecord(
            "opentargets",
            "faildrug",
            ok=True,
            facts={"target_ids": failed("opentargets", "outage")},
        ),
    )
    # An OK target_ids fact already -> genuinely done, must be skipped (not re-fetched).
    await repo.upsert_drug(
        "CHEMBL_DONE", pref_name="donedrug", maturity=DataMaturity.PARTIAL, last_enriched_at=now
    )
    await repo.save_record(
        "CHEMBL_DONE",
        SourceRecord(
            "opentargets",
            "donedrug",
            ok=True,
            facts={"target_ids": fact(["ENSG_DONE"], "opentargets")},
        ),
    )
    # The fact marks it done; its drug_target row is what a real prior backfill would have
    # left. Seed it too, so "DONE is skipped" can be asserted as "its row survives untouched".
    await repo.sync_drug_targets("CHEMBL_DONE", ["ENSG_DONE"])
    await session.commit()


@respx.mock
async def test_backfill_fills_marks_empty_done_and_retries_outages(
    session: AsyncSession, fast_client: httpx.AsyncClient, seeded: None
) -> None:
    respx.post(OT).mock(side_effect=_ot_handler)

    seen, synced = await backfill(session, client=fast_client)
    # Three candidates: HAS + NOTGT (no fact) and FAILED (its fact is source_failed, so NOT
    # done). DONE is excluded. Without the source_failed filter this would be 2 -- so this
    # count is the guard against a drug stranded by an outage never being retried.
    assert (seen, synced) == (3, 3)

    cancers = CancerRepository(session)
    # HAS was filled from OT.
    assert await cancers.catalog_drug_for_targets(["ENSG_HAS"]) == {"ENSG_HAS": "CHEMBL_HAS"}
    # FAILED was RETRIED (not skipped) and filled -- the Finding-3 fix.
    assert await cancers.catalog_drug_for_targets(["ENSG_FAIL"]) == {"ENSG_FAIL": "CHEMBL_FAILED"}

    repo = DrugRepository(session)
    # NOTGT: an EMPTY target_ids fact marks it done, with no drug_target rows.
    nfacts = {f.key: f for f in await repo.facts_for("CHEMBL_NOTGT")}
    assert nfacts["target_ids"].status is FactStatus.EMPTY
    assert await cancers.catalog_drug_for_targets(["ENSG_HAS", "ENSG_FAIL"]) != {}  # sanity

    # DONE was never a candidate: its pre-seeded ENSG_DONE row is untouched.
    assert await cancers.catalog_drug_for_targets(["ENSG_DONE"]) == {"ENSG_DONE": "CHEMBL_DONE"}


@respx.mock
async def test_backfill_second_run_is_a_no_op(
    session: AsyncSession, fast_client: httpx.AsyncClient, seeded: None
) -> None:
    respx.post(OT).mock(side_effect=_ot_handler)
    await backfill(session, client=fast_client)
    # Every candidate now carries a measured target_ids fact (OK or EMPTY) -> none re-fetched.
    seen, synced = await backfill(session, client=fast_client)
    assert (seen, synced) == (0, 0)
