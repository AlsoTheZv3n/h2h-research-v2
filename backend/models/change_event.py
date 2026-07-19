"""The change-event log: an append-only record of every real fact-value change.

The refresh cron overwrites facts in place, so without this the delta a "what changed" feed is
built from -- a phase transition, a corrected potency, a terminated trial -- is gone the moment
it is overwritten. This captures it: one row is appended whenever a stored fact's VALUE or STATUS
actually changes, for both entities (drug, cancer). NOT written on a first insert (nothing
changed yet) and NOT on the identical re-fetch that only bumps `retrieved_at` -- only a real
change is an event.

Append-only. Nothing here feeds back into the fact model or the read path; it is additive.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base
from backend.models.fact import JsonValue


class ChangeEvent(Base):
    """One observed change to a (entity, key, source) fact."""

    __tablename__ = "change_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 'drug' | 'cancer' -- which catalog the entity belongs to.
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # the ChEMBL id or the disease id, per entity_type.
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # The values before and after. NULL is a real state here (a source_failed fact carries no
    # value), so a change into or out of NULL is itself an event worth recording.
    old_value: Mapped[JsonValue | None] = mapped_column(JSONB(none_as_null=True))
    new_value: Mapped[JsonValue | None] = mapped_column(JSONB(none_as_null=True))
    # The FactStatus strings (ok / empty / source_failed) -- a status flip (ok -> source_failed)
    # is a change even when the value does not move.
    old_status: Mapped[str] = mapped_column(String(16), nullable=False)
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # The feed is read newest-first, usually scoped to one entity.
        Index("ix_change_event_entity", "entity_type", "entity_id", "detected_at"),
    )
