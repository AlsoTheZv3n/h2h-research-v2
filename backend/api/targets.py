"""Target detail brief.

The target-side twin of the cancer brief: it enriches on first open (the Open Targets reverse
query -> the cancers a target is associated with, filtered to our catalog), serves from
Postgres after, and is honest about the four brief states. Same contract as api/cancers.py,
mirrored rather than shared so the other entities are untouched.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cache import get_redis, invalidate_target_detail, target_detail_cache_key
from backend.config import get_settings
from backend.db import get_session
from backend.ingestion.base import FactStatus
from backend.repositories.targets import TargetRepository
from backend.schemas import SourcedFact, TargetDetail
from backend.services.briefs import BriefState
from backend.services.target_briefs import (
    get_or_start_target_brief,
    is_target_enriching,
    retry_target_brief,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/targets", tags=["targets"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/{ensembl_id}",
    response_model=TargetDetail,
    summary="Detail: the target's evidence brief, every fact with provenance and status",
)
async def get_target(ensembl_id: str, session: SessionDep) -> TargetDetail:
    """The brief, enriching it first if nobody ever has. Only a `ready` brief is cached."""
    settings = get_settings()
    cache_key = target_detail_cache_key(ensembl_id)
    redis = get_redis()

    try:
        cached = await redis.get(cache_key)
        if cached:
            return TargetDetail.model_validate_json(cached)
    except Exception as exc:
        # A cache miss and a dead cache look the same to the caller: degraded latency, never
        # a degraded answer.
        logger.warning("target cache read failed for %s: %s", ensembl_id, exc)

    repo = TargetRepository(session)
    target = await repo.get(ensembl_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"no target {ensembl_id}")

    state = await get_or_start_target_brief(session, ensembl_id)
    rows = await repo.facts_for(ensembl_id)

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

    # A key is "unavailable" only when *every* source for it failed -- so one source being
    # down does not read as the fact being absent.
    unavailable = sorted(
        key
        for key, entries in facts.items()
        if entries and all(f.status is FactStatus.SOURCE_FAILED for f in entries)
    )

    catalog_drugs = await repo.catalog_drugs_for_target(ensembl_id)

    detail = TargetDetail(
        ensembl_id=target.ensembl_id,
        symbol=target.symbol,
        name=target.name,
        n_cancers=target.n_cancers,
        last_enriched_at=target.last_enriched_at,
        state=state,
        refreshing=state is BriefState.READY and is_target_enriching(ensembl_id),
        facts=dict(facts),
        unavailable=unavailable,
        catalog_drugs=catalog_drugs,
    )

    # Cache only a finished brief, and not one being re-fetched right now (the retry-race
    # guard, exactly as on the cancer side).
    if state is BriefState.READY and not is_target_enriching(ensembl_id):
        try:
            await redis.set(cache_key, detail.model_dump_json(), ex=settings.cache_ttl_seconds)
        except Exception as exc:
            logger.warning("target cache write failed for %s: %s", ensembl_id, exc)

    return detail


@router.post(
    "/{ensembl_id}/retry",
    summary="Re-fetch the source for a target whose brief has source failures",
)
async def retry_target(ensembl_id: str, session: SessionDep) -> dict[str, str]:
    """Ask Open Targets again, then let the page poll for the fresh brief. Invalidates the
    cached brief first, or a retry would re-fetch in the background while the reader kept being
    served the stale, still-failed copy."""
    repo = TargetRepository(session)
    if await repo.get(ensembl_id) is None:
        raise HTTPException(status_code=404, detail=f"no target {ensembl_id}")

    await invalidate_target_detail(ensembl_id)
    state = await retry_target_brief(session, ensembl_id)
    return {"state": state.value}
