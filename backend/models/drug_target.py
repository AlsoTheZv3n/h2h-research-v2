"""Which stable target (Ensembl gene) each catalog drug acts on.

A thin many-to-many between `drug` and a target's Ensembl id, populated from the drug's
Open Targets mechanisms on enrichment. It exists for one question the cancer target
landscape asks: "does our catalog hold a drug against THIS target?" -- answered by the
Ensembl id, never the alias-prone approvedSymbol, so a renamed symbol can never make a
real link vanish or a wrong one appear.

Deliberately NOT a fact table: it carries no provenance or status of its own (the drug's
`target_ids` fact is where the source and retrieval date live). This is a derived index,
existing only to make the reverse lookup -- given an Ensembl id, which drugs hit it --
a single indexed query instead of a scan over every drug's fact JSON.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DrugTarget(Base):
    __tablename__ = "drug_target"

    drug_chembl_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("drug.chembl_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # The Ensembl gene id (ENSG...) of a target the drug acts on. Part of the composite
    # primary key: a (drug, target) pair is unique, and re-enrichment upserts it.
    target_ensembl_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    __table_args__ = (
        # The load-bearing index: the landscape join reads by target, not by drug.
        Index("ix_drug_target_ensembl", "target_ensembl_id"),
    )

    def __repr__(self) -> str:
        return f"<DrugTarget {self.drug_chembl_id}->{self.target_ensembl_id}>"
