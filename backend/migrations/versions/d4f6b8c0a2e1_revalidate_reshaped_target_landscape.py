"""revalidate cancers with a pre-reshape target_landscape fact

Revision ID: d4f6b8c0a2e1
Revises: c3e5a7b9d1f2
Create Date: 2026-07-18 18:55:00.000000

The target_landscape fact value changed shape: it used to be a bare array of targets,
and now it is {threshold, n_strong, targets} so the detail page can lead with the count
of strong associations instead of the ~12,000-with-any-evidence total. The Redis cache
key carries its own version, so stale *rendered* briefs are never served -- but the
cancer_fact rows themselves still hold the old array shape until something re-enriches
them, and an old-shape fact carries no strong count.

This back-dates last_enriched_at for exactly the cancers holding an old-shape fact, so
stale-while-revalidate re-fetches each one (lazily, on next open) and upserts the new
shape. The frontend tolerates the old array in the meantime, so nothing breaks in the
window between this migration and the revalidation. A no-op where no cancer was enriched
under the old shape (the common case for a young feature).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d4f6b8c0a2e1"
down_revision: str | None = "c3e5a7b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A fixed, far-past timestamp is stale under any freshness window, so this does not
    # need to read the app's freshness_days setting to guarantee revalidation.
    op.execute(
        """
        UPDATE cancer
           SET last_enriched_at = now() - interval '400 days'
         WHERE last_enriched_at IS NOT NULL
           AND disease_id IN (
               SELECT disease_id
                 FROM cancer_fact
                WHERE key = 'target_landscape'
                  AND jsonb_typeof(value) = 'array'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature: the pre-migration last_enriched_at values are not recorded,
    # and the only effect of the upgrade is to trigger a benign re-fetch. There is nothing
    # to restore, so downgrade is a documented no-op rather than a lie about reversibility.
    pass
