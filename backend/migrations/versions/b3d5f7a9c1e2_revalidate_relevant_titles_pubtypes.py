"""revalidate drugs whose relevant_titles predates publication types + indexed status

Revision ID: b3d5f7a9c1e2
Revises: f1a3c5e7d9b2
Create Date: 2026-07-21 16:00:00.000000

#42 enriched the `relevant_titles` fact from a list of title STRINGS to a list of OBJECTS carrying
each paper's publication type (an evidence hierarchy) and MeSH-indexed status ("not yet indexed" vs
indexed). The frontend degrades gracefully on the old shape (a string reads as a title with no
badge), and the drug cache key was bumped (v5 -> v6) so a stale rendered brief is not served -- but a
drug enriched before #42 keeps the old string-array fact until it re-enriches, and would show titles
with no publication type until it aged out of the freshness window on its own.

Same fix as the earlier revalidations: back-date last_enriched_at for any enriched drug whose
relevant_titles is still the old string-array shape, so stale-while-revalidate re-fetches each on next
open and rebuilds the fact with the per-paper signals. A no-op on a fresh DB and idempotent (a re-run
re-selects the same already-back-dated rows). Drugs with no relevant_titles are untouched -- they get
the new shape whenever their literature is next fetched anyway.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b3d5f7a9c1e2"
down_revision: str | None = "f1a3c5e7d9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An enriched drug whose relevant_titles fact is a non-empty array whose first element is a
    # STRING predates #42 (the new shape is an array of objects). A fixed far-past timestamp is stale
    # under any freshness window, so this needs no app settings.
    op.execute(
        """
        UPDATE drug d
           SET last_enriched_at = now() - interval '400 days'
         WHERE d.last_enriched_at IS NOT NULL
           AND EXISTS (
               SELECT 1
                 FROM fact f
                WHERE f.drug_chembl_id = d.chembl_id
                  AND f.key = 'relevant_titles'
                  AND jsonb_typeof(f.value) = 'array'
                  AND jsonb_array_length(f.value) > 0
                  AND jsonb_typeof(f.value -> 0) = 'string'
           )
        """
    )


def downgrade() -> None:
    # Irreversible by nature (the prior timestamps are not recorded), and the only effect is a
    # benign re-fetch, so downgrade is a documented no-op rather than a lie about reversal.
    pass
