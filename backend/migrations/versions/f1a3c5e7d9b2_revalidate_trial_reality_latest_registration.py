"""revalidate cancers whose trial-reality predates the latest-registration field

Revision ID: f1a3c5e7d9b2
Revises: a1b3c5d7e9f0
Create Date: 2026-07-21 12:00:00.000000

E3 (silent stalling) adds a `latest_registration` sub-field to the trial_reality fact (the true
most-recent CT.gov registration date, from a new sort-based sub-query) and a derived "no new trial
since YYYY" synthesis line that reads from it. The Redis cache key was bumped (v9 -> v10) so a stale
*rendered* brief is never served -- but a cancer already enriched before E3 has a trial_reality fact
with no latest_registration key, and would silently lack both the "last new trial" line and the
stalling signal until it aged out of the freshness window on its own.

Same fix as the earlier trial-reality / landscape revalidations (c4a6e8b0d2f4, d4f6b8c0a2e1):
back-date last_enriched_at for any enriched cancer whose trial_reality fact lacks the new field, so
stale-while-revalidate re-fetches each one lazily on next open and picks up the sub-query. A no-op on
a fresh DB and idempotent (a re-run re-selects the same already-back-dated rows). Cancers with a
source_failed trial_reality (value NULL, so no key) are also re-fetched -- exactly what a retry wants.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f1a3c5e7d9b2"
down_revision: str | None = "a1b3c5d7e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An enriched cancer with no trial_reality fact carrying the latest_registration key predates E3.
    # A fixed far-past timestamp is stale under any freshness window, so this needs no app settings.
    # NOT EXISTS (not NOT IN) so a NULL in the subquery cannot swallow the whole result. `value ?
    # 'latest_registration'` is false for a NULL (source_failed) value too, so those re-fetch as well.
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
                  AND f.value ? 'latest_registration'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (the prior timestamps are not recorded), and the only effect is a
    # benign re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
