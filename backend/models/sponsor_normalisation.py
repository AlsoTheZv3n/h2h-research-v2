"""The curated trial-sponsor normalisation map: a raw ClinicalTrials.gov lead-sponsor string ->
the canonical company it belongs to.

Spike S4 (amber): 12,000 oncology trials carry ~3,500 distinct raw lead-sponsor strings. DISPLAY of
the raw name is fine, but any AGGREGATE count (trials-per-sponsor, "top sponsors") is wrong without
this, because big pharma fragments across subsidiaries ~4:1 in the head (Pfizer across Seagen /
Wyeth / Array / Hospira; Roche across Genentech; J&J across a dozen Janssen entities). This maps the
curated head (~50 rows, the fragmented pharma) to a canonical name; the ~3,400-string tail is mostly
already-distinct academic centres and is left as-is (a raw string with no row normalises to itself).

The source of truth is the reviewable, version-controlled file
`backend/data/sponsor_normalisation.csv`; this table is loaded from it (see
`backend.ingestion.load_sponsor_map`), the same discipline as the disease crosswalk.

THE TRAP, encoded here and noted in the CSV: **Merck KGaA (Darmstadt, Germany)** and **Merck & Co /
MSD (US)** are DIFFERENT companies. They normalise to two DISTINCT canonicals and must never merge
-- a normaliser that collapsed them on the shared word "Merck" would be confidently wrong.
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class SponsorNormalisation(Base):
    __tablename__ = "sponsor_normalisation"

    # The exact raw ClinicalTrials.gov leadSponsor.name string (PK: one canonical per raw string).
    # 512 wide because some subsidiary strings are long ("ArQule, Inc., a subsidiary of ...").
    raw_name: Mapped[str] = mapped_column(String(512), primary_key=True)
    # The canonical company this raw string rolls up to, e.g. "Pfizer", "Roche".
    canonical_name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Why the mapping holds (an acquisition, a subsidiary) or -- for the Merck pair -- why two
    # entities must NOT merge. Reviewable, like disease_source_map.note.
    note: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<SponsorNormalisation {self.raw_name!r}->{self.canonical_name!r}>"
