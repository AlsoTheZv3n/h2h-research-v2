"""revalidate enriched targets so they gain the PubTator extracted_relations fact

Revision ID: c3d5e7f9a1b4
Revises: b1c3d5e7f9a2
Create Date: 2026-07-21 18:45:00.000000

#44 added a target source (PubTator machine-extracted gene<->disease/chemical relations) writing the
`extracted_relations` fact, and bumped the target cache key (v2 -> v3). A target enriched before #44
has no such fact and would show nothing for the block until it aged out of the freshness window.

Same fix as the sibling revalidations: back-date last_enriched_at for any enriched target that has no
extracted_relations fact yet, so stale-while-revalidate re-runs its sources on next open. A no-op on a
fresh DB and idempotent: once a target has the fact, a re-run no longer selects it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c3d5e7f9a1b4"
down_revision: str | None = "b1c3d5e7f9a2"
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
                  AND f.key = 'extracted_relations'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (prior timestamps are not recorded); the only effect is a benign
    # re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
