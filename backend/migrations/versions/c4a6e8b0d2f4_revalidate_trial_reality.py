"""revalidate cancers enriched before the trial-reality block

Revision ID: c4a6e8b0d2f4
Revises: b2e4d6f8a1c3
Create Date: 2026-07-19 12:00:00.000000

P1-T4 added a trial-reality block: a `trial_reality` fact (ClinicalTrials.gov, by condition) now
belongs on every cancer brief. The Redis cache key was bumped (v5 -> v6) so a stale *rendered*
brief is never served -- but a cancer already enriched before this block simply has no
trial_reality row at all, and would silently lack the whole block until it aged out of the
freshness window on its own.

Same fix as the target_landscape reshapes (d4f6b8c0a2e1, f9c2e4a6b8d0): back-date
last_enriched_at for any enriched cancer with no trial_reality fact, so stale-while-revalidate
re-fetches each one (lazily, on next open) and picks up the new source. A no-op on a fresh DB
(nothing enriched yet) and idempotent (a re-run re-selects the same already-back-dated rows).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c4a6e8b0d2f4"
down_revision: str | None = "b2e4d6f8a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An enriched cancer with no trial_reality fact predates the block. A fixed far-past timestamp
    # is stale under any freshness window, so this needs no app settings. NOT EXISTS (not NOT IN)
    # so a NULL in the subquery cannot swallow the whole result.
    op.execute(
        """
        UPDATE cancer c
           SET last_enriched_at = now() - interval '400 days'
         WHERE c.last_enriched_at IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM cancer_fact f
                WHERE f.disease_id = c.disease_id
                  AND f.key = 'trial_reality'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (the prior timestamps are not recorded), and the only effect is a
    # benign re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
