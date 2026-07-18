"""Which MONDO entity each external source category (Eurostat ICD-10 site, SEER site code)
corresponds to -- the curated crosswalk that lets epidemiology and survival data attach to
the cancer catalog by ID and ontology, never by name.

The source of truth is the reviewable, version-controlled file
`backend/data/disease_source_map.csv`; this table is loaded from it (see
`backend.ingestion.load_disease_map`). A row with `mondo_id` NULL is an explicitly recorded
*unmappable* category (an ICD aggregate with no single MONDO entity), kept so the decision is
visible rather than a silent omission.
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DiseaseSourceMap(Base):
    __tablename__ = "disease_source_map"

    # e.g. "eurostat" / "seer"
    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    # the source's own category code, e.g. "C33_C34" or a SEER numeric code as text
    source_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    # human-readable, e.g. "Trachea, bronchus & lung (C33-C34)" -- the UI names the entity with it
    source_label: Mapped[str] = mapped_column(String(256), nullable=False)
    # the canonical MONDO entity this category corresponds to. NULL = explicitly unmappable
    # (an aggregate with no single entity), NOT a missing row.
    mondo_id: Mapped[str | None] = mapped_column(String(32))
    # justification where the choice is non-obvious, or the reason a row is unmappable
    note: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<DiseaseSourceMap {self.source}:{self.source_code}->{self.mondo_id}>"
