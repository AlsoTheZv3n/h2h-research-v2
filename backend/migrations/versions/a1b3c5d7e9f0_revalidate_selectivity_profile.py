"""revalidate drugs enriched before the selectivity_profile fact

Revision ID: a1b3c5d7e9f0
Revises: d5e7f9a1b3c6
Create Date: 2026-07-20 15:00:00.000000

Epic A rebuilt the drug potency card: it now reads a new `selectivity_profile` fact (ranked
targets, assay-kind split) instead of `ic50_summary`, and the Redis cache version was bumped
(v2 -> v3, cache.py) so a stale *rendered* brief is never served. But a drug already enriched
before this change simply has no selectivity_profile row -- so its potency card would render the
"Not collected" honest state ("we looked, no source measured this") even though its IC50 data is
sitting, unread, under the old ic50_summary key. That mislabels present data as absent.

Same fix as the fact-reshape migrations (c4a6e8b0d2f4 trial_reality, d4f6b8c0a2e1 / f9c2e4a6b8d0
target_landscape): back-date last_enriched_at for any enriched drug that has an ic50_summary fact
but no selectivity_profile fact, so stale-while-revalidate re-enriches each one lazily on next
open and the adapter writes the new fact (chembl.py writes both keys). A no-op on a fresh DB
(nothing enriched yet) and idempotent (a re-run re-selects the same already-back-dated rows). The
committed demo fixture already carries selectivity_profile, so seeded demo drugs are not matched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a1b3c5d7e9f0"
down_revision: str | None = "d5e7f9a1b3c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An enriched drug with an ic50_summary fact but no selectivity_profile predates Epic A. A
    # fixed far-past timestamp is stale under any freshness window, so this needs no app settings.
    # NOT EXISTS (not NOT IN) so a NULL in the subquery cannot swallow the whole result. Gated on
    # HAVING an ic50_summary so a catalog-only row (never enriched, no facts) is left untouched.
    op.execute(
        """
        UPDATE drug d
           SET last_enriched_at = now() - interval '400 days'
         WHERE d.last_enriched_at IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM fact f
                WHERE f.drug_chembl_id = d.chembl_id
                  AND f.key = 'ic50_summary'
           )
           AND NOT EXISTS (
               SELECT 1 FROM fact f
                WHERE f.drug_chembl_id = d.chembl_id
                  AND f.key = 'selectivity_profile'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (the prior timestamps are not recorded), and the only effect is a
    # benign re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
