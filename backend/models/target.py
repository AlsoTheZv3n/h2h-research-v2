"""The target catalog: the gene/protein entity a drug acts on and a cancer is driven by.

The third first-class entity, mirroring `drug` and `cancer`. Keyed on the stable Ensembl
gene id (ENSG...), never the alias-prone approvedSymbol -- the same join rule the cancer
target-landscape already holds, now at the level of a whole record. The symbol is display
text; the id is identity.

A NULL `last_enriched_at` means "nobody has built this target's brief yet" -- the fourth
state, distinct from "built it and Open Targets carried no cancer association". And
`n_cancers` is NULL, not 0, until that brief is built: a target seeded from the catalog has
had its associated cancers *counted* only once it is enriched, so an un-enriched 0 would be
the None-vs-0 trap one level up -- "not yet measured" dressed as "measured, none". The
catalog loader leaves both NULL; only enrich_target fills them.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Target(Base):
    __tablename__ = "target"

    # The stable Ensembl gene id (ENSG...) -- the spine every join uses, matching
    # drug_target.target_ensembl_id and the ensembl_id carried in each cancer's target
    # landscape. A renamed approvedSymbol can never make a link vanish or a wrong one appear.
    ensembl_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # The approved gene symbol (EGFR, KRAS, STK11) -- how a researcher names a target, so
    # it leads the page and backs search. NOT NULL: a target with no symbol cannot be
    # rendered, so the catalog does not list one (the landscape uses the same basis).
    symbol: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # The descriptive approvedName ("epidermal growth factor receptor"). NULL until the
    # brief is built: the catalog seed carries only the id+symbol it already holds; the
    # reverse Open Targets query (enrich_target) fills the name.
    name: Mapped[str | None] = mapped_column(String(512), index=True)

    # How many cancers in OUR catalog this target is associated with -- the "worth listing"
    # signal and a future overview's sort key. NULL, not 0, until enriched: it is measured
    # by the reverse query filtered to the catalog, which only enrichment runs. 0 is a real
    # zero (enriched, no catalog cancer associated); NULL is "never counted".
    n_cancers: Mapped[int | None] = mapped_column(Integer, index=True)

    # NULL means the sources have never been asked to build this target's brief -- the
    # fourth state, distinct from "asked, a source failed" and "asked, found nothing".
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Target {self.ensembl_id} {self.symbol!r}>"
