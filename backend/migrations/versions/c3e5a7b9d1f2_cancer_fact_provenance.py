"""cancer fact provenance

Revision ID: c3e5a7b9d1f2
Revises: b7d2f4a1c9e3
Create Date: 2026-07-18 15:20:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3e5a7b9d1f2"
down_revision: str | None = "b7d2f4a1c9e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The disease-side twin of `fact`. The fact_status enum already exists (the drug
    # `fact` table created it), so this references it with create_type=False rather than
    # trying to CREATE TYPE a second time.
    op.create_table(
        "cancer_fact",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("disease_id", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("ok", "empty", "source_failed", name="fact_status", create_type=False),
            nullable=False,
        ),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["disease_id"],
            ["cancer.disease_id"],
            name=op.f("fk_cancer_fact_disease_id_cancer"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cancer_fact")),
        sa.UniqueConstraint("disease_id", "key", "source", name="uq_cancer_fact_disease_key_source"),
        sa.CheckConstraint(
            "status <> 'ok' OR value IS NOT NULL", name=op.f("ck_cancer_fact_ok_has_value")
        ),
        sa.CheckConstraint(
            "status <> 'source_failed' OR value IS NULL",
            name=op.f("ck_cancer_fact_failed_has_no_value"),
        ),
    )
    op.create_index(op.f("ix_cancer_fact_disease"), "cancer_fact", ["disease_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cancer_fact_disease"), table_name="cancer_fact")
    op.drop_table("cancer_fact")
