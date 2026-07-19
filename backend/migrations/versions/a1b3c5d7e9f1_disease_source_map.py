"""disease_source_map: source category -> MONDO crosswalk

Revision ID: a1b3c5d7e9f1
Revises: f9c2e4a6b8d0
Create Date: 2026-07-18 21:10:00.000000

The curated crosswalk (Eurostat ICD-10 site / SEER site code -> MONDO), loaded from the
version-controlled backend/data/disease_source_map.csv. mondo_id is nullable: NULL is an
explicitly recorded unmappable category, not a missing row.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b3c5d7e9f1"
down_revision: str | None = "f9c2e4a6b8d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "disease_source_map",
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_code", sa.String(length=32), nullable=False),
        sa.Column("source_label", sa.String(length=256), nullable=False),
        sa.Column("mondo_id", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("source", "source_code", name=op.f("pk_disease_source_map")),
    )


def downgrade() -> None:
    op.drop_table("disease_source_map")
