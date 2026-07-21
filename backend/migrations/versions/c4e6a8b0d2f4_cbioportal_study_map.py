"""cbioportal_study_map: MONDO -> cBioPortal-study crosswalk (#43)

Revision ID: c4e6a8b0d2f4
Revises: b3d5f7a9c1e2
Create Date: 2026-07-21 15:40:00.000000

The curated crosswalk (MONDO cancer entity -> the one cBioPortal study its alteration frequency
is drawn from), loaded from the version-controlled backend/data/cbioportal_study_map.csv. mondo_id
is the primary key, so one canonical study maps to an entity (samples are never pooled across
cohorts). commercial_ok gates the licence whitelist in the schema itself.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e6a8b0d2f4"
down_revision: str | None = "b3d5f7a9c1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cbioportal_study_map",
        sa.Column("mondo_id", sa.String(length=32), nullable=False),
        sa.Column("study_id", sa.String(length=128), nullable=False),
        sa.Column("source_label", sa.String(length=256), nullable=False),
        sa.Column("commercial_ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("mondo_id", name=op.f("pk_cbioportal_study_map")),
    )


def downgrade() -> None:
    op.drop_table("cbioportal_study_map")
