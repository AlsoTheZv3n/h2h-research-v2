"""Target catalog persistence. Mirrors CancerRepository's list/upsert shape.

Phase 1 (the catalog) needs only `get` and an idempotent `upsert_target`; the fact
methods (save_record, facts_for, mark_enriched) arrive with enrich_target.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Target


class TargetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, ensembl_id: str) -> Target | None:
        return await self.session.get(Target, ensembl_id)

    async def upsert_target(self, ensembl_id: str, **columns: object) -> Target:
        """Insert or update a catalog row.

        ON CONFLICT DO UPDATE, not read-modify-write: the backfill is re-runnable and must
        stay idempotent. Only the passed columns are updated, so a re-run that carries just
        the symbol never clobbers an already-enriched name / n_cancers / last_enriched_at
        back to NULL.
        """
        values = {"ensembl_id": ensembl_id, **columns}
        stmt = insert(Target).values(**values)
        update_cols = {k: getattr(stmt.excluded, k) for k in columns}
        if update_cols:
            stmt = stmt.on_conflict_do_update(index_elements=[Target.ensembl_id], set_=update_cols)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=[Target.ensembl_id])
        await self.session.execute(stmt)
        target = await self.session.get(Target, ensembl_id)
        assert target is not None
        return target
