"""Cancer overview and (minimal) detail.

The overview is the P1-T1 deliverable: a scannable, filterable, sortable index of
cancer types on the Open Targets disease spine. The detail endpoint is deliberately
thin for now -- there is no enrich_cancer job yet (that is P1-T2), so a cancer's brief
has never been built and the honest state is `not_analyzed`. It exists so a row click
navigates to a real page rather than a dead route.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.repositories.cancers import CancerRepository
from backend.schemas import CancerDetail, CancerList, CancerSummary
from backend.services.briefs import BriefState

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
    """Distinct areas, most-common first, for the overview's facet dropdown.

    Declared before /{disease_id} on purpose: a path parameter would otherwise swallow
    "therapeutic-areas" and try to resolve it as a cancer.
    """
    return await CancerRepository(session).distinct_therapeutic_areas()


@router.get(
    "/{disease_id}",
    response_model=CancerDetail,
    summary="Detail: the cancer's catalog facts (its evidence brief lands in P1-T2)",
)
async def get_cancer(disease_id: str, session: SessionDep) -> CancerDetail:
    cancer = await CancerRepository(session).get(disease_id)
    if cancer is None:
        raise HTTPException(status_code=404, detail=f"no cancer {disease_id}")

    # No enrich_cancer job exists yet (P1-T2): a brief has never been built, so the
    # honest state is not_analyzed -- never "ready with nothing", which would tell the
    # reader this cancer has no evidence when the truth is we have not looked. Once a
    # cancer has been enriched, last_enriched_at is set and the state reads READY.
    state = BriefState.READY if cancer.last_enriched_at else BriefState.NOT_ANALYZED
    return CancerDetail(
        disease_id=cancer.disease_id,
        name=cancer.name,
        therapeutic_area=cancer.therapeutic_area,
        n_drugs=cancer.n_drugs,
        n_targets=cancer.n_targets,
        last_enriched_at=cancer.last_enriched_at,
        state=state,
    )
