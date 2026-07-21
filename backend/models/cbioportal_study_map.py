"""Which cBioPortal study each MONDO cancer entity draws its alteration frequency from -- the
curated crosswalk that lets cBioPortal genomics attach to the cancer catalog by ID and ontology,
never by name.

The source of truth is the reviewable, version-controlled file
`backend/data/cbioportal_study_map.csv`; this table is loaded from it (see
`backend.ingestion.load_cbioportal_map`). It is the twin of `disease_source_map`, with three
deliberate differences that molecular data forces:

  - The primary key is `mondo_id`, so ONE canonical study maps to an entity (not several rows
    per entity). A cancer's alteration frequency must come from a single cohort or samples are
    double-counted -- the PK enforces that at the schema level.
  - There are no NULL-mondo "unmappable" rows. cBioPortal coverage is a small whitelist (~two
    dozen major tumour types); a cancer with no row is simply NOT_MEASURED, which the absence of
    a row already says. (disease_source_map records unmappable ICD aggregates because ITS source
    enumerates categories; here the catalog is the enumeration and cBioPortal is the subset.)
  - `commercial_ok` is an explicit, machine-checkable column, not prose in a note. cBioPortal
    serves some studies under a commercial-use restriction (ODbL permits this per study); the
    crosswalk only lists studies that are freely redistributable, and the flag makes that a
    reviewable guarantee rather than a curator's memory. The ingest adapter refuses any row whose
    flag is false, so a study that changes status cannot silently leak restricted data.

Rollup is deliberately NOT applied to this source (unlike epidemiology/survival): a molecular
profile is subtype-specific -- cutaneous melanoma's driver spectrum is not acral melanoma's -- so
rolling a parent cohort's frequencies onto a molecularly-distinct child would mislead even when
labelled. Attachment is EXACT MONDO match only.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class CBioPortalStudyMap(Base):
    __tablename__ = "cbioportal_study_map"

    # The catalog cancer this study's alteration frequency attaches to. PRIMARY KEY: one
    # canonical study per entity, so samples are never pooled across cohorts (double-counting).
    mondo_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # The cBioPortal study id fetched, e.g. "skcm_tcga_pan_can_atlas_2018".
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Human-readable, e.g. "Cutaneous Melanoma — TCGA PanCancer Atlas" -- the UI names the cohort
    # with it, so a reader always sees WHICH cohort a frequency came from.
    source_label: Mapped[str] = mapped_column(String(256), nullable=False)
    # True only for studies with no commercial-use restriction (ODbL default). The ingest adapter
    # refuses a row whose flag is false: the whitelist is enforced in code, not just curation.
    commercial_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # The curation justification: the OncoTree -> NCIt -> MONDO xref bridge that verifies the row,
    # plus the licence status. Reviewable, like disease_source_map.note.
    note: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<CBioPortalStudyMap {self.mondo_id}->{self.study_id}>"
