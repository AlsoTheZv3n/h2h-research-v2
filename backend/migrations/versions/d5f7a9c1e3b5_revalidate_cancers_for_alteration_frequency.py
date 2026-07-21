"""revalidate enriched cancers so they gain the cBioPortal alteration_frequency fact

Revision ID: d5f7a9c1e3b5
Revises: c4e6a8b0d2f4
Create Date: 2026-07-21 16:10:00.000000

#43 added a new cancer source (cBioPortal somatic-mutation frequency) writing the
`alteration_frequency` fact, and bumped the cancer cache key (v10 -> v11) so a stale rendered brief
is not served. But a cancer enriched before #43 has no alteration_frequency fact at all and would
show nothing for the block until it aged out of the freshness window on its own.

Same fix as the earlier revalidations: back-date last_enriched_at for any enriched cancer that has
no alteration_frequency fact yet, so stale-while-revalidate re-runs its sources on next open and the
new source writes the fact (the measured frequency for a mapped cohort, or the honest "unmapped"
state for the ~98% of the catalog with no matched study). A no-op on a fresh DB and idempotent: once
a cancer has the fact, a re-run no longer selects it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d5f7a9c1e3b5"
down_revision: str | None = "c4e6a8b0d2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An enriched cancer with no alteration_frequency fact predates #43. A fixed far-past timestamp
    # is stale under any freshness window, so this needs no app settings.
    op.execute(
        """
        UPDATE cancer c
           SET last_enriched_at = now() - interval '400 days'
         WHERE c.last_enriched_at IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM cancer_fact f
                WHERE f.disease_id = c.disease_id
                  AND f.key = 'alteration_frequency'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (the prior timestamps are not recorded), and the only effect is a
    # benign re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
