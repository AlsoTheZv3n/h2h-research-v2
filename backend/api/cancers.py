"""Cancer overview and detail brief.

The overview (P1-T1) is a scannable index on the Open Targets disease spine. The detail
(P1-T2) is the disease-side twin of the drug brief: it enriches on first open, serves
from Postgres after, and is honest about the four brief states. Same contract as
api/drugs.py, mirrored rather than shared so the drug side is untouched.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cache import cancer_detail_cache_key, get_redis, invalidate_cancer_detail
from backend.config import get_settings
from backend.db import get_session
from backend.ingestion.base import FactStatus
from backend.repositories.cancers import CancerRepository
from backend.schemas import CancerDetail, CancerList, CancerSummary, SourcedFact
from backend.services.briefs import BriefState
from backend.services.cancer_briefs import (
    get_or_start_cancer_brief,
    is_cancer_enriching,
    retry_cancer_brief,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cancers", tags=["cancers"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

CancerSortField = Literal["drugs", "targets", "name", "area"]
SortOrder = Literal["asc", "desc"]


@router.get("", response_model=CancerList, summary="Overview: a scannable index of cancer types")
async def list_cancers(
    session: SessionDep,
    q: Annotated[
        str | None,
        Query(description="Search cancer name or disease id. Partial, case-insensitive."),
    ] = None,
    therapeutic_area: Annotated[
        str | None, Query(description="Exact therapeutic area, e.g. 'hematologic disorder'")
    ] = None,
    has_drugs: Annotated[
        bool | None,
        Query(description="Only cancers that have (or lack) a drug/clinical candidate programme"),
    ] = None,
    sort: Annotated[
        CancerSortField, Query(description="Column to sort by. Default: number of drugs.")
    ] = "drugs",
    order: Annotated[SortOrder, Query(description="Sort direction")] = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CancerList:
    repo = CancerRepository(session)
    rows, total = await repo.list_cancers(
        q=q,
        therapeutic_area=therapeutic_area,
        has_drugs=has_drugs,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return CancerList(
        items=[CancerSummary.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/therapeutic-areas",
    response_model=list[str],
    summary="The area facet's options: therapeutic areas present in the catalog",
)
async def list_therapeutic_areas(session: SessionDep) -> list[str]:
    """Declared before /{disease_id}, or a path param would swallow "therapeutic-areas"."""
    return await CancerRepository(session).distinct_therapeutic_areas()


@router.get(
    "/{disease_id}",
    response_model=CancerDetail,
    summary="Detail: the evidence brief, every fact with provenance and status",
)
async def get_cancer(disease_id: str, session: SessionDep) -> CancerDetail:
    """The brief, enriching it first if nobody ever has. Only a `ready` brief is cached."""
    settings = get_settings()
    cache_key = cancer_detail_cache_key(disease_id)
    redis = get_redis()

    try:
        cached = await redis.get(cache_key)
        if cached:
            return CancerDetail.model_validate_json(cached)
    except Exception as exc:
        # A cache miss and a dead cache look the same to the caller: degraded latency,
        # never a degraded answer.
        logger.warning("cancer cache read failed for %s: %s", disease_id, exc)

    repo = CancerRepository(session)
    cancer = await repo.get(disease_id)
    if cancer is None:
        raise HTTPException(status_code=404, detail=f"no cancer {disease_id}")

    state = await get_or_start_cancer_brief(session, disease_id)
    rows = await repo.facts_for(disease_id)

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

    # A key is "unavailable" only when *every* source for it failed -- so one source
    # being down does not read as the fact being absent.
    unavailable = sorted(
        key
        for key, entries in facts.items()
        if entries and all(f.status is FactStatus.SOURCE_FAILED for f in entries)
    )

    detail = CancerDetail(
        disease_id=cancer.disease_id,
        name=cancer.name,
        therapeutic_area=cancer.therapeutic_area,
        n_drugs=cancer.n_drugs,
        n_targets=cancer.n_targets,
        last_enriched_at=cancer.last_enriched_at,
        state=state,
        refreshing=state is BriefState.READY and is_cancer_enriching(disease_id),
        facts=dict(facts),
        unavailable=unavailable,
    )

    # Cache only a finished brief, and not one being re-fetched right now (the retry-race
    # guard, exactly as on the drug side).
    if state is BriefState.READY and not is_cancer_enriching(disease_id):
        try:
            await redis.set(cache_key, detail.model_dump_json(), ex=settings.cache_ttl_seconds)
        except Exception as exc:
            logger.warning("cancer cache write failed for %s: %s", disease_id, exc)

    return detail


@router.post(
    "/{disease_id}/retry",
    summary="Re-fetch every source for a cancer whose brief has source failures",
)
async def retry_cancer(disease_id: str, session: SessionDep) -> dict[str, str]:
    """Ask the sources again, then let the page poll for the fresh brief. Invalidates the
    cached brief first, or a retry would re-fetch in the background while the reader kept
    being served the stale, still-failed copy."""
    repo = CancerRepository(session)
    if await repo.get(disease_id) is None:
        raise HTTPException(status_code=404, detail=f"no cancer {disease_id}")

    await invalidate_cancer_detail(disease_id)
    state = await retry_cancer_brief(session, disease_id)
    return {"state": state.value}
