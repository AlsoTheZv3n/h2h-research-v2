"""Drug overview and detail brief."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cache import detail_cache_key, get_redis, invalidate_detail
from backend.config import get_settings
from backend.db import get_session
from backend.domain.structure import render_svg
from backend.domain.synthesis import drug_synthesis
from backend.ingestion.base import FactStatus
from backend.models import DataMaturity
from backend.repositories import DrugRepository
from backend.repositories.drugs import is_small_molecule
from backend.schemas import (
    DrugDetail,
    DrugList,
    DrugSummary,
    FacetCount,
    SourcedFact,
    SynthesisStatement,
)
from backend.services.briefs import BriefState, get_or_start_brief, is_enriching, retry_brief

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drugs", tags=["drugs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


SortField = Literal["data", "name", "phase", "target", "class", "indication"]
SortOrder = Literal["asc", "desc"]


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
    modality: Annotated[
        str | None, Query(description="Exact drug type, e.g. 'Small molecule', 'Antibody'")
    ] = None,
    maturity: Annotated[
        DataMaturity | None,
        Query(description="Data completeness: index_only, partial, or full"),
    ] = None,
    has_target: Annotated[
        bool | None, Query(description="Only drugs with (or without) an annotated target")
    ] = None,
    target_class: Annotated[
        str | None,
        Query(
            description="Exact target family, e.g. 'Kinase'. 'unclassified' selects rows "
            "with no class recorded."
        ),
    ] = None,
    include_out_of_scope: Annotated[
        bool,
        Query(
            description="Include drugs marked non-oncology by catalog scoping. "
            "Off by default: the catalog is oncology."
        ),
    ] = False,
    sort: Annotated[
        SortField, Query(description="Column to sort by. Default: data completeness.")
    ] = "data",
    order: Annotated[SortOrder, Query(description="Sort direction")] = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DrugList:
    repo = DrugRepository(session)
    rows, total = await repo.list_drugs(
        q=q,
        target=target,
        max_phase=max_phase,
        modality=modality,
        maturity=maturity,
        has_target=has_target,
        target_class=target_class,
        include_out_of_scope=include_out_of_scope,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return DrugList(
        items=[DrugSummary.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/target-classes",
    response_model=list[str],
    summary="The target-class facet's options: families present in the catalog",
)
async def list_target_classes(session: SessionDep) -> list[str]:
    """Distinct target families, most-common first, for the overview's facet dropdown.

    Declared before /{chembl_id} on purpose: a path parameter would otherwise swallow
    "target-classes" and try to resolve it as a drug. The client appends its own
    "Unclassified" option; this returns only the classes that actually exist.
    """
    return await DrugRepository(session).distinct_target_classes()


@router.get(
    "/facets",
    response_model=dict[str, list[FacetCount]],
    summary="Per-facet option counts for the overview, given the current filters",
)
async def drug_facets(
    session: SessionDep,
    q: Annotated[str | None, Query(description="Same free-text search as the listing")] = None,
    target: Annotated[str | None, Query()] = None,
    max_phase: Annotated[int | None, Query(ge=0, le=4)] = None,
    modality: Annotated[str | None, Query()] = None,
    maturity: Annotated[DataMaturity | None, Query()] = None,
    has_target: Annotated[bool | None, Query()] = None,
    target_class: Annotated[str | None, Query()] = None,
    include_out_of_scope: Annotated[bool, Query()] = False,
) -> dict[str, list[FacetCount]]:
    """For each categorical/boolean facet, how many drugs match every OTHER active filter, grouped
    by that facet's values (its own selection excluded, so the count reads as "what selecting this
    option would give"). Takes the SAME filter params as the listing; drives the "(N)" beside each
    option. Declared before /{chembl_id} so the path parameter does not swallow "facets".
    """
    counts = await DrugRepository(session).facet_counts(
        q=q,
        target=target,
        max_phase=max_phase,
        modality=modality,
        maturity=maturity,
        has_target=has_target,
        target_class=target_class,
        include_out_of_scope=include_out_of_scope,
    )
    return {
        facet: [FacetCount(value=v, count=n) for v, n in options]
        for facet, options in counts.items()
    }


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
    cache_key = detail_cache_key(chembl_id)
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

    # The page-level "so what" (C2): derived threshold statements over the facts, each linking to
    # its block. Computed server-side from a fact's value only when that source answered OK, so an
    # absent/failed/empty fact yields no statement (never a defaulted one).
    def ok_fact(key: str) -> Any:
        entries = facts.get(key)
        return entries[0].value if entries and entries[0].status is FactStatus.OK else None

    synthesis = [
        SynthesisStatement(**s)
        for s in drug_synthesis(
            max_phase=ok_fact("max_phase"),
            selectivity=ok_fact("selectivity_profile"),
            n_trials=ok_fact("n_trials"),
            has_terminated=ok_fact("has_terminated"),
        )
    ]

    detail = DrugDetail(
        chembl_id=drug.chembl_id,
        pref_name=drug.pref_name,
        maturity=drug.maturity,
        drug_type=drug.drug_type,
        # Answered here, with the same predicate the maturity classifier uses. Left to
        # the client it becomes a second copy of the rule, and the obvious guess --
        # "index_only and no SMILES means biologic" -- is wrong for the 87 catalog
        # drugs that are small molecules ChEMBL has no structure for.
        is_small_molecule=is_small_molecule(drug.drug_type),
        has_structure=bool(drug.smiles),
        smiles=drug.smiles,
        state=state,
        # A READY brief with a refresh in flight is being revalidated (stale-while-
        # revalidate): the reader sees the stored facts now, and the client can poll for
        # the fresh ones. Not the same as `enriching`, where there are no facts yet.
        refreshing=state is BriefState.READY and is_enriching(chembl_id),
        last_enriched_at=drug.last_enriched_at,
        facts=dict(facts),
        unavailable=unavailable,
        synthesis=synthesis,
    )

    # Only cache a finished brief, and not one whose sources are being re-fetched right
    # now. The second clause closes a retry race: a reader can read this drug as READY
    # (its facts still the old, failed ones) an instant before a retry starts, then land
    # here and re-cache that stale brief just after the retry invalidated it. Re-checking
    # is_enriching immediately before the write means an in-flight retry (which stays
    # marked until it commits) suppresses the stale write; the retry's own post-commit
    # invalidation then covers the sliver where even this check could not.
    if state is BriefState.READY and not is_enriching(chembl_id):
        try:
            await redis.set(cache_key, detail.model_dump_json(), ex=settings.cache_ttl_seconds)
        except Exception as exc:
            logger.warning("cache write failed for %s: %s", chembl_id, exc)

    return detail


@router.post(
    "/{chembl_id}/retry",
    summary="Re-fetch every source for a drug whose brief has source failures",
)
async def retry_drug(chembl_id: str, session: SessionDep) -> dict[str, str]:
    """Ask the sources again, then let the page poll for the fresh brief.

    Invalidates the cached brief first: a READY brief is cached for the TTL, and a
    retry that left the cache in place would re-fetch in the background while the reader
    kept being served the stale, still-failed copy -- the retry would look like it did
    nothing until the cache expired.
    """
    repo = DrugRepository(session)
    if await repo.get(chembl_id) is None:
        raise HTTPException(status_code=404, detail=f"no drug {chembl_id}")

    await invalidate_detail(chembl_id)
    state = await retry_brief(session, chembl_id)
    return {"state": state.value}
