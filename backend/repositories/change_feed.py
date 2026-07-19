"""The change feed: append a fact's value/status changes as enrichment writes them, and read
them back. The write side is called by the drug and cancer save paths just before their upsert,
while the previous value is still in the table.

Best-effort, not exactly-once: enrichment is deduped per entity (one run at a time via the
in-flight guard), so concurrent writes to one fact are rare -- but the feed carries no unique
constraint, so a race could in principle double-log a transition or skip a middle one. That is
acceptable for an append-only "what changed" log; the value is capturing the delta at all, which
the in-place refresh would otherwise discard. Demo/fixture seeding (seed_demo) writes facts
directly and is deliberately NOT fed here -- re-seeding a fixture is not a source change."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from backend.ingestion.base import Fact
from backend.models import ChangeEvent
from backend.models.cancer_fact import CancerFactRow
from backend.models.fact import FactRow
from backend.models.target_fact import TargetFactRow

# The two fact tables share the (key, source, value, status) shape the feed reads.
FactModel = type[FactRow] | type[CancerFactRow] | type[TargetFactRow]


async def log_fact_changes(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    model: FactModel,
    id_col: InstrumentedAttribute[str],
    facts: Mapping[str, Fact],
) -> int:
    """Append one change event per fact whose stored VALUE or STATUS differs from what is about
    to be written. Never for a first insert (nothing stored yet), never for an identical re-fetch
    (only `retrieved_at` moves). Must be called BEFORE the upsert, while the old value is present.
    Returns the number of events appended.
    """
    if not facts:
        return 0
    rows = (
        await session.execute(
            select(model.key, model.source, model.value, model.status).where(
                id_col == entity_id, model.key.in_(list(facts))
            )
        )
    ).all()
    stored = {(r.key, r.source): (r.value, r.status) for r in rows}

    logged = 0
    for key, f in facts.items():
        prev = stored.get((key, f.source))
        if prev is None:
            continue  # first time this (key, source) is stored -> not a change
        old_value, old_status = prev
        if old_value == f.value and old_status == f.status:
            continue  # identical re-fetch: retrieved_at bumps, but the answer did not move
        session.add(
            ChangeEvent(
                entity_type=entity_type,
                entity_id=entity_id,
                key=key,
                source=f.source,
                old_value=old_value,
                new_value=f.value,
                old_status=str(old_status.value),
                new_status=str(f.status.value),
            )
        )
        logged += 1
    return logged


async def recent_changes(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> Sequence[ChangeEvent]:
    """The change feed, newest first, optionally scoped to an entity or a time window."""
    q = select(ChangeEvent).order_by(ChangeEvent.detected_at.desc(), ChangeEvent.id.desc())
    if entity_type is not None:
        q = q.where(ChangeEvent.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(ChangeEvent.entity_id == entity_id)
    if since is not None:
        q = q.where(ChangeEvent.detected_at >= since)
    return (await session.execute(q.limit(limit))).scalars().all()
