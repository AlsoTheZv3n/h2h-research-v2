"""revalidate enriched targets so they gain the cBioPortal target_alteration_frequency fact

Revision ID: e7a9c1b3d5f6
Revises: d5f7a9c1e3b5
Create Date: 2026-07-21 16:30:00.000000

#43 added a second target source (this gene's cBioPortal mutation frequency across the cancers it
drives) writing the `target_alteration_frequency` fact, and bumped the target cache key (v1 -> v2).
A target enriched before #43 has no such fact and would show nothing for the block until it aged
out of the freshness window on its own.

Same fix as the sibling revalidations: back-date last_enriched_at for any enriched target that has
no target_alteration_frequency fact yet, so stale-while-revalidate re-runs its sources on next open.
A no-op on a fresh DB and idempotent: once a target has the fact, a re-run no longer selects it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e7a9c1b3d5f6"
down_revision: str | None = "d5f7a9c1e3b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE target t
           SET last_enriched_at = now() - interval '400 days'
         WHERE t.last_enriched_at IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM target_fact f
                WHERE f.ensembl_id = t.ensembl_id
                  AND f.key = 'target_alteration_frequency'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (prior timestamps are not recorded); the only effect is a benign
    # re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
