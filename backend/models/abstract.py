"""Literature abstracts, held locally for retrieval and never redistributed.

Read `NOTICE.md` before touching this table. The short version: NLM does not own the
abstracts PubMed serves and says so explicitly, so nobody has cleared republishing
them. Fetching them into the database on your own machine is what E-utilities is
for; committing them, serving them over the API, or rendering them as text is the
line. `text` must never leave this process -- it exists to be embedded and to be
read by the chat model, and what comes back out is a synthesis plus a citation.

The same three-state discipline as `fact` applies, for the same reason. A PubMed
record with no abstract is extremely common -- editorials, letters, meeting reports
-- and "this paper has no abstract" is a measurement, not a failure. Collapsing it
into the same NULL as "we could not fetch this" would make the ingest either retry
forever or never retry, and there would be no way to tell which was right.

    row present, text set      the abstract, fetched on that date
    row present, text NULL     fetched; this record genuinely has no abstract
    no row                     never fetched, or the fetch failed -- and in that
                               case the drug's pubmed facts say source_failed
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.embeddings import EMBEDDING_DIM
from backend.models.base import Base


class Abstract(Base):
    """One PubMed record. Keyed by PMID, not by drug.

    A paper about osimertinib resistance is a paper about EGFR too, and the same
    PMID surfaces for several drugs. Keying by PMID stores its text and its vector
    once; `drug_abstract` carries the relationships. Storing per drug instead would
    re-embed identical text once per drug that cites it.
    """

    __tablename__ = "abstract"

    pmid: Mapped[str] = mapped_column(String(16), primary_key=True)

    # Titles are metadata and safe to show; `text` is not. They are deliberately
    # different kinds of thing living in one row, and only one of them is servable.
    title: Mapped[str | None] = mapped_column(Text)

    # NULL means "this record has no abstract", never "we did not look" -- absence of
    # the whole row means that.
    text: Mapped[str | None] = mapped_column(Text)

    journal: Mapped[str | None] = mapped_column(String(512))
    year: Mapped[int | None] = mapped_column()

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # An embedding without text is a vector pointing at nothing: it would match a
        # query, get retrieved, and hand the model an empty document to ground on.
        # Text without an embedding is merely unindexed and harmless, but it means an
        # embed step was skipped, so both directions are pinned.
        CheckConstraint(
            "(text IS NULL) = (embedding IS NULL)",
            name="embedding_iff_text",
        ),
        # HNSW over cosine. The vectors arrive L2-normalised from bge, so cosine and
        # inner product rank identically here; cosine is the honest name for what we
        # mean and stays correct if a future model stops normalising.
        Index(
            "ix_abstract_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<Abstract {self.pmid} text={'yes' if self.text else 'none'}>"


class DrugAbstract(Base):
    """Which drug's literature search turned up which PMID."""

    __tablename__ = "drug_abstract"

    drug_chembl_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("drug.chembl_id", ondelete="CASCADE"), primary_key=True
    )
    pmid: Mapped[str] = mapped_column(
        String(16), ForeignKey("abstract.pmid", ondelete="CASCADE"), primary_key=True
    )
    # Where this PMID sat in the relevance ranking PubMed returned for this drug.
    # Kept because it is PubMed's opinion, not ours, and it is the only ordering
    # signal we get for free.
    rank: Mapped[int] = mapped_column()

    __table_args__ = (Index("ix_drug_abstract_drug", "drug_chembl_id"),)
