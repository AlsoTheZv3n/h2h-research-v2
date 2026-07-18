"""drug_target: which Ensembl target each drug acts on

Revision ID: e7a1c3d5f9b2
Revises: d4f6b8c0a2e1
Create Date: 2026-07-18 19:45:00.000000

A thin many-to-many derived from each drug's Open Targets mechanisms, so the cancer target
landscape can answer "does our catalog hold a drug against this target?" by stable Ensembl
id. Indexed on the target id because that join reads by target, not by drug.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1c3d5f9b2"
down_revision: str | None = "d4f6b8c0a2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drug_target",
        sa.Column("drug_chembl_id", sa.String(length=32), nullable=False),
        sa.Column("target_ensembl_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["drug_chembl_id"],
            ["drug.chembl_id"],
            name=op.f("fk_drug_target_drug_chembl_id_drug"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "drug_chembl_id", "target_ensembl_id", name=op.f("pk_drug_target")
        ),
    )
    op.create_index("ix_drug_target_ensembl", "drug_target", ["target_ensembl_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_drug_target_ensembl", table_name="drug_target")
    op.drop_table("drug_target")
