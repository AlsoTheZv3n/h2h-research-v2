"""The cancer catalog: the overview's index columns for the disease entity.

Mirrors `drug.py` on purpose -- a flat, denormalized read model the overview can scan
without joining a fact table, built on the same honest-states discipline. This is the
disease half of a drug+cancer-centric tool; the drug half is untouched.

A NULL `last_enriched_at` means "nobody has built this cancer's brief yet", a state
distinct from "built it and the sources carried nothing" -- the same None-vs-0
distinction the whole codebase turns on, at the level of the whole record.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Cancer(Base):
    __tablename__ = "cancer"

    # Open Targets' canonical disease id -- the spine the whole expansion joins on.
    # Predominantly MONDO_ (the platform migrated disease ids off EFO, which is why the
    # spike's legacy EFO ids read as null), with a residue of EFO_ ids OT still keys
    # some diseases by. Whichever prefix OT returns *is* the id, so the column is named
    # for what it holds -- a disease id -- not one ontology. The T6 weave crosswalks
    # every other source (CIViC's DOID, ClinicalTrials.gov's condition text) back to
    # this id, never to a name: "NSCLC" vs "non-small cell lung carcinoma" string-
    # matched is the molecules[0] failure class, confidently wrong.
    disease_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True, nullable=False)

    # The organ-system / therapeutic area, the overview's main facet ("respiratory or
    # thoracic disease", "hematologic disorder"). NULL when Open Targets annotates none.
    therapeutic_area: Mapped[str | None] = mapped_column(String(256), index=True)

    # The two Open Targets signals, measured at catalog time, that a cancer is worth
    # listing at all: the seed keeps only rows with a drug/clinical candidate OR an
    # associated target, because the cancer ontology root has 1,744 descendants and a
    # quarter carry no evidence (organ-system rollups, ultra-rare subtypes). Indexed so
    # the overview can facet and sort -- narrow to "has a drug programme", rank by it.
    # NOT NULL: both are always measured, and 0 is a real zero, not "unknown".
    n_drugs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    n_targets: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    # NULL means the sources have never been asked to build this cancer's brief -- the
    # fourth state, distinct from "asked, a source failed" and "asked, found nothing".
    # The catalog loader leaves it NULL; only enrich_cancer (P1-T2) sets it. Reading a
    # never-analyzed cancer as "no evidence" would be the founding bug, one level up.
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Cancer {self.disease_id} {self.name!r}>"
