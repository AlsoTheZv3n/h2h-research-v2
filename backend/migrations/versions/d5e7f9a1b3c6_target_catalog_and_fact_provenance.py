"""target catalog and fact provenance

Revision ID: d5e7f9a1b3c6
Revises: c4a6e8b0d2f4
Create Date: 2026-07-19 21:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5e7f9a1b3c6"
down_revision: str | None = "c4a6e8b0d2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The target half of the entity model, mirroring `cancer`. Keyed on the stable Ensembl
    # gene id. `symbol` is NOT NULL (a target with no symbol cannot be rendered); `name`
    # and `n_cancers` are nullable -- both are filled by enrich_target, and an un-enriched
    # n_cancers of 0 would be "not yet measured" dressed as "measured, none" (None != 0).
    # last_enriched_at stays NULL until the brief is built, the same never-analyzed marker
    # `drug` and `cancer` carry.
    op.create_table(
        "target",
        sa.Column("ensembl_id", sa.String(length=32), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("n_cancers", sa.Integer(), nullable=True),
        sa.Column("last_enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(op.f("ix_target_symbol"), "target", ["symbol"], unique=False)
    op.create_index(op.f("ix_target_name"), "target", ["name"], unique=False)
    op.create_index(op.f("ix_target_n_cancers"), "target", ["n_cancers"], unique=False)
    op.create_index(
        op.f("ix_target_last_enriched_at"), "target", ["last_enriched_at"], unique=False
    )

    # The target-side twin of `fact` / `cancer_fact`. The fact_status enum already exists
    # (the drug `fact` table created it), so this references it with create_type=False.
    op.create_table(
        "target_fact",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ensembl_id", sa.String(length=32), nullable=False),
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
            ["ensembl_id"],
            ["target.ensembl_id"],
            name=op.f("fk_target_fact_ensembl_id_target"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_target_fact")),
        sa.UniqueConstraint(
            "ensembl_id", "key", "source", name="uq_target_fact_ensembl_key_source"
        ),
        sa.CheckConstraint(
            "status <> 'ok' OR value IS NOT NULL", name=op.f("ck_target_fact_ok_has_value")
        ),
        sa.CheckConstraint(
            "status <> 'source_failed' OR value IS NULL",
            name=op.f("ck_target_fact_failed_has_no_value"),
        ),
    )
    op.create_index(op.f("ix_target_fact_ensembl"), "target_fact", ["ensembl_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_target_fact_ensembl"), table_name="target_fact")
    op.drop_table("target_fact")
    op.drop_index(op.f("ix_target_last_enriched_at"), table_name="target")
    op.drop_index(op.f("ix_target_n_cancers"), table_name="target")
    op.drop_index(op.f("ix_target_name"), table_name="target")
    op.drop_index(op.f("ix_target_symbol"), table_name="target")
    op.drop_table("target")
