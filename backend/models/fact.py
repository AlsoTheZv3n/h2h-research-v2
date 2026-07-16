"""The fact table: every stored value with its source, status and provenance.

This is where `None != 0` stops being a convention and becomes a constraint. A row
can say three different things, and the schema keeps them apart:

    status=ok             value is set     the source measured this
    status=empty          value is 0/[]/"" the source measured, and the answer is nothing
    status=source_failed  value is NULL    we never measured; `error` says why

A CHECK constraint enforces that a failed fact carries no value, so no future code
path can quietly write a zero where an outage belongs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.ingestion.base import FactStatus
from backend.models.base import Base

# What a fact's value may be: a SMILES string, an int count, a list of targets, a
# nested potency summary.
type JsonValue = dict[str, object] | list[object] | str | int | float | bool


class FactRow(Base):
    """One (drug, key, source) assertion.

    Keyed by source as well as key on purpose: ChEMBL and Open Targets both assert a
    mechanism of action, and keeping both is what makes cross-source agreement
    checkable later. Overwriting one with the other would destroy the evidence.
    """

    __tablename__ = "fact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drug_chembl_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("drug.chembl_id", ondelete="CASCADE"), nullable=False
    )

    # e.g. "smiles", "n_trials", "moa", "ic50_summary"
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    # JSONB, because facts are heterogeneous: a SMILES string, an int count, a list
    # of targets, a nested potency summary. NULL here is ambiguous on its own --
    # `status` is what disambiguates it.
    #
    # none_as_null is load-bearing: by default SQLAlchemy encodes Python None as the
    # JSON scalar `null`, which is a *value*, so `value IS NULL` would be false and
    # the CHECK constraints below would never fire. One None, two meanings -- the
    # very confusion this table exists to prevent, one layer down.
    value: Mapped[JsonValue | None] = mapped_column(JSONB(none_as_null=True))

    status: Mapped[FactStatus] = mapped_column(
        Enum(
            FactStatus,
            name="fact_status",
            native_enum=True,
            # Without this SQLAlchemy labels the PG type with the member *names*
            # ("SOURCE_FAILED"), not the StrEnum values ("source_failed") -- and the
            # CHECK constraints below, which compare against the values, would never
            # match. Pin the labels to the values.
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )

    source_url: Mapped[str | None] = mapped_column(String(1024))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Only meaningful when status = source_failed.
    error: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("drug_chembl_id", "key", "source", name="uq_fact_drug_key_source"),
        Index("ix_fact_drug", "drug_chembl_id"),
        CheckConstraint(
            "status <> 'source_failed' OR value IS NULL",
            name="failed_has_no_value",
        ),
        CheckConstraint(
            "status <> 'ok' OR value IS NOT NULL",
            name="ok_has_value",
        ),
    )

    def __repr__(self) -> str:
        return f"<FactRow {self.drug_chembl_id}.{self.key}@{self.source}={self.status}>"
