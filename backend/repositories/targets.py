"""Target catalog persistence. Mirrors CancerRepository's list/upsert shape."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import SourceRecord
from backend.models import DrugTarget, Target, TargetFactRow
from backend.repositories.change_feed import log_fact_changes


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

    async def mark_enriched(
        self,
        ensembl_id: str,
        when: datetime,
        *,
        name: str | None = None,
        n_cancers: int | None = None,
    ) -> None:
        """Stamp last_enriched_at, and set name / n_cancers when they were actually measured.

        A plain UPDATE, not an upsert -- the NOT NULL `symbol` column would make a partial
        INSERT ... ON CONFLICT reject the candidate tuple before the conflict redirects to
        UPDATE (the same reason cancer.mark_enriched is a plain UPDATE). last_enriched_at is
        always stamped ("we looked"), but name and n_cancers are set ONLY when not None: on
        an Open Targets outage they arrive None and the last measured values must survive,
        not be blanked -- the None-vs-0 discipline. n_cancers=0 IS a measurement (enriched,
        no catalog cancer) and is written.
        """
        values: dict[str, object] = {"last_enriched_at": when}
        if name is not None:
            values["name"] = name
        if n_cancers is not None:
            values["n_cancers"] = n_cancers
        await self.session.execute(
            update(Target).where(Target.ensembl_id == ensembl_id).values(**values)
        )

    async def save_record(self, ensembl_id: str, record: SourceRecord) -> None:
        """Persist every fact of one source's answer for one target.

        Mirrors CancerRepository.save_record: a source_failed row is written like any other,
        so an outage lands on the record rather than being mistaken for an absence. Upserts on
        (target, key, source), so re-enrichment refreshes in place.
        """
        # Log real value/status changes BEFORE the upsert overwrites the previous value.
        await log_fact_changes(
            self.session,
            entity_type="target",
            entity_id=ensembl_id,
            model=TargetFactRow,
            id_col=TargetFactRow.ensembl_id,
            facts=record.facts,
        )
        for key, f in record.facts.items():
            stmt = insert(TargetFactRow).values(
                ensembl_id=ensembl_id,
                key=key,
                source=f.source,
                value=f.value,
                status=f.status,
                source_url=f.source_url,
                retrieved_at=f.retrieved_at,
                error=f.error,
                confidence=f.confidence,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_target_fact_ensembl_key_source",
                set_={
                    "value": stmt.excluded.value,
                    "status": stmt.excluded.status,
                    "source_url": stmt.excluded.source_url,
                    "retrieved_at": stmt.excluded.retrieved_at,
                    "error": stmt.excluded.error,
                    "confidence": stmt.excluded.confidence,
                },
            )
            await self.session.execute(stmt)

    async def facts_for(self, ensembl_id: str) -> Sequence[TargetFactRow]:
        result = await self.session.execute(
            select(TargetFactRow)
            .where(TargetFactRow.ensembl_id == ensembl_id)
            .order_by(TargetFactRow.key)
        )
        return result.scalars().all()

    async def catalog_drugs_for_target(self, ensembl_id: str) -> list[str]:
        """The ChEMBL ids of catalog drugs that act on this target -- the reverse of the cancer
        landscape's catalog-link, joined on the stable Ensembl id (never the symbol).

        Sorted, so the page renders a stable list of links. An empty list is an honest "no drug
        in OUR catalog hits this target" -- NOT "unexploited" (the world's answer, from Open
        Targets); it just means we hold no such drug to link to.
        """
        result = await self.session.execute(
            select(DrugTarget.drug_chembl_id)
            .where(DrugTarget.target_ensembl_id == ensembl_id)
            .order_by(DrugTarget.drug_chembl_id)
        )
        return list(result.scalars().all())

    async def enrichment_targets(
        self,
        *,
        limit: int | None = None,
        ensembl_id: str | None = None,
        only_unenriched: bool = False,
        stale_before: datetime | None = None,
    ) -> list[Target]:
        """The targets a bulk enrich run should touch, selected over last_enriched_at (the
        never-touched marker AND the freshness clock), mirroring enrich_cancer_catalog."""
        if ensembl_id:
            query = select(Target).where(Target.ensembl_id == ensembl_id)
        else:
            query = select(Target).order_by(
                func.coalesce(Target.n_cancers, 0).desc(), Target.ensembl_id
            )
            conds: list[ColumnElement[bool]] = []
            if only_unenriched:
                conds.append(Target.last_enriched_at.is_(None))
            if stale_before is not None:
                conds.append(Target.last_enriched_at < stale_before)
            if conds:
                query = query.where(or_(*conds))
            if limit:
                query = query.limit(limit)
        return list((await self.session.execute(query)).scalars().all())
