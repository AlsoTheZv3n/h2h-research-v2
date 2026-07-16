"""The drug catalog: the overview's index columns.

Deliberately flat and denormalized. The overview is a light, scannable table and must
not join across the fact table to render. Every column here is also present as a
`Fact` with full provenance -- this table is the read model, `fact` is the record.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DataMaturity(StrEnum):
    """How complete this drug's evidence brief actually is.

    Data maturity, not clinical maturity -- clinical stage lives in `max_phase`.
    This is what keeps the overview honest: an ADC appears in the list, but says
    out loud that we cannot carry a structure or binding card for it, rather than
    rendering empty cards that look like missing data.
    """

    FULL = "full"
    """Structure + potency + mechanism: every card the detail view promises."""

    PARTIAL = "partial"
    """Resolved with a structure, but some cards would be empty."""

    INDEX_ONLY = "index_only"
    """In the catalog, no brief. Biologics/ADCs land here -- their data model is v2."""


class Drug(Base):
    __tablename__ = "drug"

    # ChEMBL's ID is the natural key: it is what the sources cross-reference each
    # other by, and what Open Targets resolves a drug to.
    chembl_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    pref_name: Mapped[str | None] = mapped_column(String(512), index=True)

    smiles: Mapped[str | None] = mapped_column(String)
    mw: Mapped[float | None] = mapped_column(Float)
    alogp: Mapped[float | None] = mapped_column(Float)
    hbd: Mapped[int | None] = mapped_column(Integer)
    hba: Mapped[int | None] = mapped_column(Integer)
    psa: Mapped[float | None] = mapped_column(Float)
    ro5_violations: Mapped[int | None] = mapped_column(Integer)

    # "Small molecule", "Antibody drug conjugate", ... -- drives maturity and, in the
    # UI, whether structure/binding cards are offered at all.
    drug_type: Mapped[str | None] = mapped_column(String(128), index=True)
    # ChEMBL's 0-4 int. Open Targets' maximumClinicalStage is a *string enum* and is
    # kept as a fact, never merged into this column -- see the spike's findings.
    max_phase: Mapped[int | None] = mapped_column(Integer, index=True)
    primary_target: Mapped[str | None] = mapped_column(String(64), index=True)
    primary_indication: Mapped[str | None] = mapped_column(String(512))

    maturity: Mapped[DataMaturity] = mapped_column(
        Enum(
            DataMaturity,
            name="data_maturity",
            native_enum=True,
            # Label the PG type with the StrEnum values ("index_only"), not the member
            # names ("INDEX_ONLY"), so the database reads the way the API does.
            values_callable=lambda enum: [m.value for m in enum],
        ),
        default=DataMaturity.INDEX_ONLY,
        nullable=False,
        index=True,
    )

    # NULL means the sources have never been asked about this drug -- a fourth state,
    # distinct from "asked, and a source failed" and from "asked, and the answer is
    # nothing". The catalog loader leaves it NULL; only enrichment sets it. Reading a
    # never-analyzed drug as "no data" would be the None-vs-0 confusion at the level
    # of the whole record.
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # The overview's default filters: by target and by phase.
        Index("ix_drug_target_phase", "primary_target", "max_phase"),
    )

    def __repr__(self) -> str:
        return f"<Drug {self.chembl_id} {self.pref_name!r}>"
