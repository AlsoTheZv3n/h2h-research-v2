"""Cancer catalog persistence. Mirrors DrugRepository's list/upsert shape."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Cancer

# The columns the overview's headers can sort by. Anything else falls back to n_drugs
# rather than erroring on a bad ?sort= value. Default is n_drugs desc: in a drug-
# intelligence tool the cancers with the most therapeutic activity are the ones a
# reader most likely came for, so they lead.
_SORT_COLUMNS = {
    "drugs": Cancer.n_drugs,
    "targets": Cancer.n_targets,
    "name": Cancer.name,
    "area": Cancer.therapeutic_area,
}


class CancerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, disease_id: str) -> Cancer | None:
        return await self.session.get(Cancer, disease_id)

    async def upsert_cancer(self, disease_id: str, **columns: object) -> Cancer:
        """Insert or update a catalog row.

        ON CONFLICT DO UPDATE, not read-modify-write: the loader is re-run with
        --only-missing to fill gaps and must stay idempotent under a re-run.
        """
        values = {"disease_id": disease_id, **columns}
        stmt = insert(Cancer).values(**values)
        update_cols = {k: getattr(stmt.excluded, k) for k in columns}
        if update_cols:
            stmt = stmt.on_conflict_do_update(index_elements=[Cancer.disease_id], set_=update_cols)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=[Cancer.disease_id])
        await self.session.execute(stmt)
        cancer = await self.session.get(Cancer, disease_id)
        assert cancer is not None
        return cancer

    async def list_cancers(
        self,
        *,
        q: str | None = None,
        therapeutic_area: str | None = None,
        has_drugs: bool | None = None,
        sort: str = "drugs",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Cancer], int]:
        """One page of the overview, filtered and sorted in SQL, plus the total.

        Filter -> sort -> page, all in Postgres, with the total counted over the
        *filtered* set (not len()'d over the page): the same discipline the drug
        overview holds, and the same bug it refuses -- a page length mistaken for a
        total.
        """
        filters = []
        if q:
            # Partial, case-insensitive, across the two things someone types: the
            # cancer's name or its disease id. Substring, because a search box is used
            # one keystroke at a time and an exact match reads as broken until the last.
            pattern = f"%{q.strip()}%"
            filters.append(or_(Cancer.name.ilike(pattern), Cancer.disease_id.ilike(pattern)))
        if therapeutic_area:
            # A facet set from a known value: exact but case-insensitive.
            filters.append(func.lower(Cancer.therapeutic_area) == therapeutic_area.strip().lower())
        if has_drugs is not None:
            # "Has a drug programme" vs not -- the facet that turns the full catalog
            # (targets or drugs) into just the cancers with therapeutics.
            filters.append(Cancer.n_drugs > 0 if has_drugs else Cancer.n_drugs == 0)

        total = await self.session.scalar(select(func.count()).select_from(Cancer).where(*filters))

        column = _SORT_COLUMNS.get(sort, Cancer.n_drugs)
        ordered = (column.desc() if order == "desc" else column.asc()).nullslast()
        rows = await self.session.execute(
            select(Cancer)
            .where(*filters)
            # disease_id last as a stable tiebreaker: every sort key is non-unique or
            # nullable, so without it tied rows have no defined order and a paging
            # client can see one twice while missing another. See DrugRepository.
            .order_by(ordered, Cancer.disease_id)
            .limit(limit)
            .offset(offset)
        )
        return rows.scalars().all(), int(total or 0)

    async def distinct_therapeutic_areas(self) -> list[str]:
        """The area facet's options: areas actually present, most-common first.

        Data-driven, not a hardcoded enum -- which areas exist depends on what the
        catalog holds. NULL is excluded: "no area" is not a facet a reader would pick.
        """
        result = await self.session.execute(
            select(Cancer.therapeutic_area, func.count())
            .where(Cancer.therapeutic_area.isnot(None))
            .group_by(Cancer.therapeutic_area)
            .order_by(func.count().desc(), Cancer.therapeutic_area)
        )
        return [row[0] for row in result.all()]
