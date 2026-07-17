"""in_scope for oncology catalog scoping

Revision ID: 9fa3f02ee6bf
Revises: 81d9d1e507eb
Create Date: 2026-07-17 21:07:15.751786

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9fa3f02ee6bf"
down_revision: str | None = "81d9d1e507eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable with no default: existing rows stay NULL ("not yet evaluated"), which the
    # overview shows. Only the scoping pass sets True/False, so nothing is hidden until a
    # drug has actually been judged out of scope.
    op.add_column("drug", sa.Column("in_scope", sa.Boolean(), nullable=True))
    op.create_index(op.f("ix_drug_in_scope"), "drug", ["in_scope"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_drug_in_scope"), table_name="drug")
    op.drop_column("drug", "in_scope")
