"""Drug overview and detail brief."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cache import get_redis
from backend.config import get_settings
from backend.db import get_session
from backend.ingestion.base import FactStatus
from backend.repositories import DrugRepository
from backend.schemas import DrugDetail, DrugList, DrugSummary, SourcedFact

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drugs", tags=["drugs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=DrugList, summary="Overview: a scannable index of drug programs")
async def list_drugs(
    session: SessionDep,
    target: Annotated[str | None, Query(description="Filter by primary target symbol")] = None,
    max_phase: Annotated[
        int | None, Query(ge=0, le=4, description="Minimum clinical phase")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DrugList:
    repo = DrugRepository(session)
    rows, total = await repo.list_drugs(
        target=target, max_phase=max_phase, limit=limit, offset=offset
    )
    return DrugList(
        items=[DrugSummary.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{chembl_id}",
    response_model=DrugDetail,
    summary="Detail: the evidence brief, every fact with provenance and status",
)
async def get_drug(chembl_id: str, session: SessionDep) -> DrugDetail:
    settings = get_settings()
    cache_key = f"drug:detail:{chembl_id}"
    redis = get_redis()

    try:
        cached = await redis.get(cache_key)
        if cached:
            return DrugDetail.model_validate_json(cached)
    except Exception as exc:
        # A cache miss and a dead cache must look the same to the caller: degraded
        # latency, never a degraded answer.
        logger.warning("cache read failed for %s: %s", chembl_id, exc)

    repo = DrugRepository(session)
    drug = await repo.get(chembl_id)
    if drug is None:
        raise HTTPException(status_code=404, detail=f"no drug {chembl_id}")

    rows = await repo.facts_for(chembl_id)

    facts: dict[str, list[SourcedFact]] = defaultdict(list)
    for row in rows:
        facts[row.key].append(
            SourcedFact(
                value=row.value,
                status=row.status,
                source=row.source,
                source_url=row.source_url,
                retrieved_at=row.retrieved_at,
                error=row.error,
                confidence=row.confidence,
            )
        )

    # A key is only "unavailable" when *every* source for it failed. If ChEMBL is
    # down but Open Targets answered, we have a mechanism -- flagging it as missing
    # would be as wrong as hiding that ChEMBL failed.
    unavailable = sorted(
        key
        for key, entries in facts.items()
        if entries and all(f.status is FactStatus.SOURCE_FAILED for f in entries)
    )

    detail = DrugDetail(
        chembl_id=drug.chembl_id,
        pref_name=drug.pref_name,
        maturity=drug.maturity,
        facts=dict(facts),
        unavailable=unavailable,
    )

    try:
        await redis.set(cache_key, detail.model_dump_json(), ex=settings.cache_ttl_seconds)
    except Exception as exc:
        logger.warning("cache write failed for %s: %s", chembl_id, exc)

    return detail
