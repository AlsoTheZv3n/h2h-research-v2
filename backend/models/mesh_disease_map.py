"""MeSH disease id -> MONDO catalog entity, for the PubTator disease join (#44).

PubTator keys diseases by MeSH (e.g. Melanoma -> D008545); our catalog is MONDO. This table
bridges them so a machine-extracted gene->disease relation can LINK to our cancer page when the
disease is one we hold, by ID (never by name string).

DERIVED, not hand-curated (unlike disease_source_map): each row is MONDO's own MeSH cross-reference,
read from the ontology for every catalog cancer that carries one (~211 of 1324 -- the major cancers;
fine subtypes often lack a MeSH xref, and their extracted mentions simply render UNLINKED, never
dropped). The file `backend/data/mesh_disease_map.csv` records the derivation; regenerating it
is a mechanical re-read of the MONDO xrefs, not a curation decision.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class MeshDiseaseMap(Base):
    __tablename__ = "mesh_disease_map"

    # The MeSH descriptor/id PubTator uses for the disease, e.g. "D008545". PRIMARY KEY: one MONDO
    # per MeSH id (the derivation takes MONDO's primary MeSH xref, so this holds).
    mesh_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    # The catalog cancer this MeSH id bridges to.
    mondo_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # The MONDO label, so a link can name the target entity without a second lookup.
    mondo_label: Mapped[str] = mapped_column(String(256), nullable=False)

    def __repr__(self) -> str:
        return f"<MeshDiseaseMap {self.mesh_id}->{self.mondo_id}>"
