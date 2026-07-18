"""The cancer fact table: a cancer's evidence, with source, status and provenance.

The disease-side twin of `fact`. Same shape, same CHECK constraints, same None!=0
discipline -- a separate table only because it hangs off `cancer.disease_id` instead of
`drug.chembl_id`. Kept parallel rather than merged into one polymorphic table so the
drug side is untouched and each foreign key stays real (a fact cannot point at a drug
that is actually a cancer).
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
from backend.models.fact import JsonValue


class CancerFactRow(Base):
    """One (cancer, key, source) assertion. See FactRow for the reasoning behind every
    column -- this is the same table with a disease foreign key."""

    __tablename__ = "cancer_fact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    disease_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("cancer.disease_id", ondelete="CASCADE"), nullable=False
    )

    # e.g. "target_landscape", "pipeline", "trial_reality"
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    # JSONB with none_as_null, so `value IS NULL` is a real null the CHECK below can
    # test -- not SQLAlchemy's default JSON scalar `null`, which is a value. See fact.py.
    value: Mapped[JsonValue | None] = mapped_column(JSONB(none_as_null=True))

    status: Mapped[FactStatus] = mapped_column(
        Enum(
            FactStatus,
            name="fact_status",
            native_enum=True,
            values_callable=lambda enum: [m.value for m in enum],
            # The enum type already exists (created by the drug `fact` migration); this
            # table only references it, it does not re-create it.
            create_type=False,
        ),
        nullable=False,
    )

    source_url: Mapped[str | None] = mapped_column(String(1024))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("disease_id", "key", "source", name="uq_cancer_fact_disease_key_source"),
        Index("ix_cancer_fact_disease", "disease_id"),
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
        return f"<CancerFactRow {self.disease_id}.{self.key}@{self.source}={self.status}>"
