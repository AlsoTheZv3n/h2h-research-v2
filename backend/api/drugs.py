"""Drug overview and detail brief."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cache import get_redis
from backend.config import get_settings
from backend.db import get_session
from backend.domain.structure import render_svg
from backend.ingestion.base import FactStatus
from backend.repositories import DrugRepository
from backend.schemas import DrugDetail, DrugList, DrugSummary, SourcedFact
from backend.services.briefs import BriefState, get_or_start_brief

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drugs", tags=["drugs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=DrugList, summary="Overview: a scannable index of drug programs")
async def list_drugs(
    session: SessionDep,
    q: Annotated[
        str | None,
        Query(description="Search drug name, ChEMBL id or target. Partial, case-insensitive."),
    ] = None,
    target: Annotated[
        str | None, Query(description="Exact primary target symbol, e.g. KRAS")
    ] = None,
    max_phase: Annotated[
        int | None, Query(ge=0, le=4, description="Minimum clinical phase")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DrugList:
    repo = DrugRepository(session)
    rows, total = await repo.list_drugs(
        q=q, target=target, max_phase=max_phase, limit=limit, offset=offset
    )
    return DrugList(
        items=[DrugSummary.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{chembl_id}/structure.svg",
    response_class=Response,
    summary="The molecule, rendered. 404 when there is no structure to draw.",
    responses={200: {"content": {"image/svg+xml": {}}}},
)
async def get_structure(chembl_id: str, session: SessionDep) -> Response:
    """Render the drug's SMILES to SVG.

    A 404 here is a real answer, not an error: biologics have no SMILES, and that
    absence is a finding the detail page states plainly. The alternative -- serving
    a blank image -- would be the same lie this codebase keeps refusing to tell.
    """
    drug = await DrugRepository(session).get(chembl_id)
    if drug is None:
        raise HTTPException(status_code=404, detail=f"no drug {chembl_id}")
    if not drug.smiles:
        raise HTTPException(status_code=404, detail=f"{chembl_id} has no structure")

    svg = render_svg(drug.smiles)
    if svg is None:
        raise HTTPException(status_code=404, detail=f"{chembl_id}: SMILES is not renderable")

    return Response(
        content=svg,
        media_type="image/svg+xml",
        # Structures change only when the catalog is re-ingested.
        headers={"Cache-Control": f"public, max-age={get_settings().cache_ttl_seconds}"},
    )


@router.get(
    "/{chembl_id}",
    response_model=DrugDetail,
    summary="Detail: the evidence brief, every fact with provenance and status",
)
async def get_drug(chembl_id: str, session: SessionDep) -> DrugDetail:
    """The brief, enriching it first if nobody ever has.

    Only a `ready` brief is cached. An enriching one is a moving target, and caching
    "we haven't looked yet" for an hour would strand the drug in that state long
    after its facts landed.
    """
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

    state = await get_or_start_brief(session, chembl_id)
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
        state=state,
        last_enriched_at=drug.last_enriched_at,
        facts=dict(facts),
        unavailable=unavailable,
    )

    # Only cache a finished brief. Caching an in-flight one would pin "analyzing" in
    # front of every reader for the whole TTL, long after the facts had landed.
    if state is BriefState.READY:
        try:
            await redis.set(cache_key, detail.model_dump_json(), ex=settings.cache_ttl_seconds)
        except Exception as exc:
            logger.warning("cache write failed for %s: %s", chembl_id, exc)

    return detail
