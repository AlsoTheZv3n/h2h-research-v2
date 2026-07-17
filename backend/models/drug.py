"""The drug catalog: the overview's index columns.

Deliberately flat and denormalized. The overview is a light, scannable table and must
not join across the fact table to render. Every column here is also present as a
`Fact` with full provenance -- this table is the read model, `fact` is the record.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, Float, Index, Integer, String, func
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
    # Indexed because the overview lets a reader sort by it. The other faceted columns
    # (drug_type, max_phase, primary_target, maturity) already carry an index; this was
    # the one sortable column without one.
    primary_indication: Mapped[str | None] = mapped_column(String(512), index=True)
    # The primary target's protein family ("Kinase", "Hydrolase", ...), promoted from
    # Open Targets. Indexed because the overview facets on it. NULL means no class was
    # annotated -- the overview reads that as "Unclassified", a state distinct from
    # "never enriched" (which the whole row's last_enriched_at NULL records).
    target_class: Mapped[str | None] = mapped_column(String(128), index=True)

    # Whether this drug belongs in an oncology catalog. Three states, on purpose:
    #   NULL   not yet evaluated -- shown, because ignorance must not hide a drug
    #   True   evaluated, in scope
    #   False  evaluated, out of scope -- a blunt substring match pulled in a non-cancer
    #          drug (a statin, a contrast agent); the overview hides it by default
    # Reversible by construction: the scoping pass only ever sets this, and re-running
    # with a tuned rule (or clearing it) restores a drug. Indexed for the default filter.
    in_scope: Mapped[bool | None] = mapped_column(Boolean, index=True)

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

    # The same distinction for the literature index, and it needs its own column for
    # exactly the reason the one above exists.
    #
    # Without it, "nobody has fetched this drug's abstracts" and "we fetched them and
    # PubMed has nothing" are both *no rows in drug_abstract* -- one observation,
    # two opposite meanings, and the retriever cannot tell the reader which. That is
    # this project's founding bug, and it got written into the literature layer by
    # the same hand that wrote the comments warning about it. Found in review.
    #
    # NULL means never fetched. Set means we asked on that date; whether anything
    # came back is then a question about the links, which is a different question.
    literature_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
