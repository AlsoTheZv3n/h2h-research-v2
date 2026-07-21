"""revalidate enriched cancers so their trial_reality gains the normalised by_sponsor distribution

Revision ID: a9c1b3d5e7f8
Revises: f8b0d2e4a6c8
Create Date: 2026-07-21 17:10:00.000000

#39 added a normalised `by_sponsor` distribution (top sponsors, subsidiaries merged) inside the
trial_reality fact, and bumped the cancer cache key (v11 -> v12). A cancer enriched before #39 has a
trial_reality fact WITHOUT by_sponsor and would show nothing for that dimension until it aged out.

Same fix as the sibling revalidations: back-date last_enriched_at for any enriched cancer whose
trial_reality fact is an object lacking a `by_sponsor` key, so stale-while-revalidate re-fetches it
and the source writes the new distribution. Leaves alone cancers with no trial_reality fact and the
measured-EMPTY (null-value) trial_reality facts (a zero-trials cancer has no sponsors to normalise).
Idempotent: once the key is present, a re-run no longer selects the cancer.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a9c1b3d5e7f8"
down_revision: str | None = "f8b0d2e4a6c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE cancer c
           SET last_enriched_at = now() - interval '400 days'
         WHERE c.last_enriched_at IS NOT NULL
           AND EXISTS (
               SELECT 1
                 FROM cancer_fact f
                WHERE f.disease_id = c.disease_id
                  AND f.key = 'trial_reality'
                  AND f.value IS NOT NULL
                  AND jsonb_typeof(f.value) = 'object'
                  AND NOT (f.value ? 'by_sponsor')
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (prior timestamps are not recorded); the only effect is a benign
    # re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
