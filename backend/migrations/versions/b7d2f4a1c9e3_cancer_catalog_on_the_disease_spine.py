"""cancer catalog on the Open Targets disease spine

Revision ID: b7d2f4a1c9e3
Revises: 9fa3f02ee6bf
Create Date: 2026-07-18 12:40:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2f4a1c9e3"
down_revision: str | None = "9fa3f02ee6bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The disease half of the entity model, mirroring `drug`. Keyed on the Open Targets
    # canonical disease id (mostly MONDO). n_drugs/n_targets are NOT NULL with a server
    # default of 0 -- a measured zero, never "unknown". last_enriched_at stays NULL
    # until enrich_cancer (P1-T2) builds a brief, the same never-analyzed marker `drug`
    # carries.
    op.create_table(
        "cancer",
        sa.Column("disease_id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("therapeutic_area", sa.String(length=256), nullable=True),
        sa.Column("n_drugs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("n_targets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_cancer_name"), "cancer", ["name"], unique=False)
    op.create_index(op.f("ix_cancer_therapeutic_area"), "cancer", ["therapeutic_area"], unique=False)
    op.create_index(op.f("ix_cancer_n_drugs"), "cancer", ["n_drugs"], unique=False)
    op.create_index(op.f("ix_cancer_n_targets"), "cancer", ["n_targets"], unique=False)
    op.create_index(op.f("ix_cancer_last_enriched_at"), "cancer", ["last_enriched_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cancer_last_enriched_at"), table_name="cancer")
    op.drop_index(op.f("ix_cancer_n_targets"), table_name="cancer")
    op.drop_index(op.f("ix_cancer_n_drugs"), table_name="cancer")
    op.drop_index(op.f("ix_cancer_therapeutic_area"), table_name="cancer")
    op.drop_index(op.f("ix_cancer_name"), table_name="cancer")
    op.drop_table("cancer")
