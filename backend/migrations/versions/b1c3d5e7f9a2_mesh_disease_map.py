"""mesh_disease_map: MeSH disease id -> MONDO, for the PubTator disease join (#44)

Revision ID: b1c3d5e7f9a2
Revises: a9c1b3d5e7f8
Create Date: 2026-07-21 18:30:00.000000

The derived MeSH-id -> MONDO bridge (MONDO's own MeSH cross-references), loaded from
backend/data/mesh_disease_map.csv, so a machine-extracted PubTator gene->disease relation can link
to our cancer page by ID. mesh_id is the primary key (one MONDO per MeSH id).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c3d5e7f9a2"
down_revision: str | None = "a9c1b3d5e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mesh_disease_map",
        sa.Column("mesh_id", sa.String(length=16), nullable=False),
        sa.Column("mondo_id", sa.String(length=32), nullable=False),
        sa.Column("mondo_label", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("mesh_id", name=op.f("pk_mesh_disease_map")),
    )


def downgrade() -> None:
    op.drop_table("mesh_disease_map")
