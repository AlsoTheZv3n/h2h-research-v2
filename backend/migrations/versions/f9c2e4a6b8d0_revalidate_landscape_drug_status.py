"""revalidate cancers whose target_landscape predates the drugged flag

Revision ID: f9c2e4a6b8d0
Revises: e7a1c3d5f9b2
Create Date: 2026-07-18 20:30:00.000000

R4 reshaped the target_landscape fact again: each displayed target gained an Ensembl id and
a drugged/in-development/unexploited status. The Redis cache key was bumped (v4 -> v5) so a
stale *rendered* brief is never served -- but the cancer_fact rows themselves still hold the
pre-flag shape until something re-enriches them, and a pre-flag fact has no ensembl_id (so
every catalog link vanishes) and no drug_status (so every target reads "unknown").

This is the exact gap the earlier reshape's migration (d4f6b8c0a2e1) closed, and it needs the
same fix: back-date last_enriched_at for cancers holding a pre-flag target_landscape, so
stale-while-revalidate re-fetches each one (lazily, on next open) under the R4 shape. Without
it, a cancer enriched within the freshness window would silently lack the whole feature until
it aged out on its own. A no-op where no cancer was enriched before R4.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f9c2e4a6b8d0"
down_revision: str | None = "e7a1c3d5f9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A pre-flag fact's JSON does not contain the string "drug_status" anywhere (each target
    # gained that key in R4); a post-flag fact does. This text test is shape-agnostic -- it
    # catches both the object shape (v4) and any still-array shape not yet revalidated by
    # d4f6b8c0a2e1 -- where a jsonb path test would have to special-case each. A fixed far-
    # past timestamp is stale under any freshness window, so this needs no app settings.
    op.execute(
        """
        UPDATE cancer
           SET last_enriched_at = now() - interval '400 days'
         WHERE last_enriched_at IS NOT NULL
           AND disease_id IN (
               SELECT disease_id
                 FROM cancer_fact
                WHERE key = 'target_landscape'
                  AND status = 'ok'
                  AND value::text NOT LIKE '%drug_status%'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (the prior timestamps are not recorded), and the only effect is
    # a benign re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
