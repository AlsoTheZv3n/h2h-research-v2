"""target_class for the overview facet

Revision ID: 81d9d1e507eb
Revises: e325e959f222
Create Date: 2026-07-17 20:13:32.729950

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "81d9d1e507eb"
down_revision: str | None = "e325e959f222"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable with no backfill: existing rows read as "Unclassified" until enrichment
    # (or the backfill pass) fills them from Open Targets. NULL is the honest default --
    # it means "no class recorded yet", not a fabricated bucket.
    op.add_column("drug", sa.Column("target_class", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_drug_target_class"), "drug", ["target_class"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_drug_target_class"), table_name="drug")
    op.drop_column("drug", "target_class")
