"""The target_class backfill: fill the column for drugs enriched before it existed.

Drives the real backfill against a real database with Open Targets mocked at the HTTP
boundary, and pins the three things that make it honest: it touches only rows that
have a target and no class, it promotes a real class into the column, and a target
Open Targets carries no class for stays NULL (with an EMPTY provenance fact) rather
than being filled with a placeholder.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.backfill_target_class import backfill
from backend.ingestion.base import FactStatus
from backend.models import DataMaturity, Drug
from backend.repositories import DrugRepository

OT = "https://api.platform.opentargets.org/api/v4/graphql"

# name (as fetched, lowercased) -> Open Targets drug id
_NAME_TO_ID = {"havinib": "CHEMBL_HAS", "nocla": "CHEMBL_NOCLS"}

# drug id -> the drug payload's targetClass shape. HAS carries a class; NOCLS carries
# a target with an empty class list (the "no class recorded" case).
_TARGET_CLASS: dict[str, list[dict[str, str]]] = {
    "CHEMBL_HAS": [{"label": "Enzyme", "level": "l1"}, {"label": "Kinase", "level": "l2"}],
    "CHEMBL_NOCLS": [],
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
                                "targets": [
                                    {"approvedSymbol": "SYM", "targetClass": _TARGET_CLASS[drug_id]}
                                ],
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
    """Three drugs: one to fill, one with no class in OT, one with no target at all.

    Starts from an empty catalog because these tests assert the *count* of backfill
    candidates, and the `session` fixture only truncates at teardown -- a preceding
    test that seeds through the `api` fixture (its own sessionmaker, no truncation)
    would otherwise leave rows that count as extra candidates here. TRUNCATE gives this
    test the clean slate its counts assume; the session fixture truncates again after.
    """
    await session.execute(text("TRUNCATE TABLE drug CASCADE"))
    repo = DrugRepository(session)
    await repo.upsert_drug(
        "CHEMBL_HAS",
        pref_name="havinib",
        primary_target="EGFR",
        maturity=DataMaturity.PARTIAL,
    )
    await repo.upsert_drug(
        "CHEMBL_NOCLS",
        pref_name="nocla",
        primary_target="SYM",
        maturity=DataMaturity.PARTIAL,
    )
    # No target -> not a candidate. If the backfill fetched it, the mock's search would
    # miss and it would still be untouched, but it must never even be selected.
    await repo.upsert_drug(
        "CHEMBL_NOTGT",
        pref_name="notarget",
        primary_target=None,
        maturity=DataMaturity.INDEX_ONLY,
    )
    await session.commit()


@respx.mock
async def test_backfill_fills_only_targeted_rows_and_never_invents_a_class(
    session: AsyncSession, fast_client: httpx.AsyncClient, seeded: None
) -> None:
    respx.post(OT).mock(side_effect=_ot_handler)

    seen, written = await backfill(session, client=fast_client)
    assert (seen, written) == (2, 1), "two candidates, one real class written"

    repo = DrugRepository(session)

    has = await session.get(Drug, "CHEMBL_HAS")
    assert has is not None
    await session.refresh(has)
    assert has.target_class == "Kinase"  # promoted, at the l2 family level
    facts = {f.key: f for f in await repo.facts_for("CHEMBL_HAS")}
    assert facts["target_class"].status is FactStatus.OK
    assert facts["target_class"].value == "Kinase"

    # No class in OT -> column stays NULL, and the fact records EMPTY, not a value.
    nocls = await session.get(Drug, "CHEMBL_NOCLS")
    assert nocls is not None
    await session.refresh(nocls)
    assert nocls.target_class is None
    nfacts = {f.key: f for f in await repo.facts_for("CHEMBL_NOCLS")}
    assert nfacts["target_class"].status is FactStatus.EMPTY
    assert nfacts["target_class"].value is None

    # The untargeted drug was never a candidate: no class, no fact.
    notgt = await session.get(Drug, "CHEMBL_NOTGT")
    assert notgt is not None
    await session.refresh(notgt)
    assert notgt.target_class is None
    assert await repo.facts_for("CHEMBL_NOTGT") == []


@respx.mock
async def test_backfill_is_resumable_and_a_second_run_is_a_no_op_for_filled_rows(
    session: AsyncSession, fast_client: httpx.AsyncClient, seeded: None
) -> None:
    respx.post(OT).mock(side_effect=_ot_handler)

    await backfill(session, client=fast_client)
    # Second pass: the filled row is no longer a candidate; only the class-less one is
    # re-tried (and still yields nothing). Selecting on target_class IS NULL is what
    # makes the pass resumable instead of re-doing settled work.
    seen, written = await backfill(session, client=fast_client)
    assert (seen, written) == (1, 0)
