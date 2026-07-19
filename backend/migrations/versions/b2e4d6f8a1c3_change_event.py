"""change_event: append-only log of real fact-value changes

Revision ID: b2e4d6f8a1c3
Revises: a1b3c5d7e9f1
Create Date: 2026-07-19 13:10:00.000000

Additive: a new table only. The refresh cron overwrites facts in place, so the delta a
"what changed" feed needs is captured here as enrichment writes it, or lost retroactively.
No change to the fact model or the read path.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2e4d6f8a1c3"
down_revision: str | None = "a1b3c5d7e9f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "change_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("old_value", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("new_value", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("old_status", sa.String(length=16), nullable=False),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_event")),
    )
    op.create_index(
        "ix_change_event_entity",
        "change_event",
        ["entity_type", "entity_id", "detected_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_change_event_entity", table_name="change_event")
    op.drop_table("change_event")
