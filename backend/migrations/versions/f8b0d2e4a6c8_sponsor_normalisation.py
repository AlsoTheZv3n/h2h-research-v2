"""sponsor_normalisation: raw ClinicalTrials.gov lead-sponsor -> canonical company (#39)

Revision ID: f8b0d2e4a6c8
Revises: e7a9c1b3d5f6
Create Date: 2026-07-21 17:00:00.000000

The curated map (raw leadSponsor.name -> canonical), loaded from the version-controlled
backend/data/sponsor_normalisation.csv, so aggregate sponsor counts merge a company's subsidiaries
instead of undercounting big pharma ~4:1. raw_name is the primary key (one canonical per raw string).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8b0d2e4a6c8"
down_revision: str | None = "e7a9c1b3d5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sponsor_normalisation",
        sa.Column("raw_name", sa.String(length=512), nullable=False),
        sa.Column("canonical_name", sa.String(length=256), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("raw_name", name=op.f("pk_sponsor_normalisation")),
    )


def downgrade() -> None:
    op.drop_table("sponsor_normalisation")
